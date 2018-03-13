#  ___________________________________________________________________________
#
#  Pyomo: Python Optimization Modeling Objects
#  Copyright 2017 National Technology and Engineering Solutions of Sandia, LLC
#  Under the terms of Contract DE-NA0003525 with National Technology and
#  Engineering Solutions of Sandia, LLC, the U.S. Government retains certain
#  rights in this software.
#  This software is distributed under the 3-clause BSD License.
#  ___________________________________________________________________________

import pyutilib.th as unittest

from pyomo.repn import generate_standard_repn
from pyomo.environ import *
#from pyomo.core.base import expr as EXPR
from pyomo.gdp import *
import pyomo.gdp.tests.models as models

import pyomo.opt
linear_solvers = pyomo.opt.check_available_solvers(
    'glpk','cbc','gurobi','cplex')

import random
from six import iteritems, iterkeys

# DEBUG
from nose.tools import set_trace

EPS = pyomo.gdp.plugins.chull.EPS

class TwoTermDisj(unittest.TestCase):
    # make sure that we are using coopr3 expressions...
    def setUp(self):
        # set seed to test unique namer
        random.seed(666)

    def test_transformation_block(self):
        m = models.makeTwoTermDisj_Nonlinear()
        TransformationFactory('gdp.chull').apply_to(m)

        transBlock = m._pyomo_gdp_chull_relaxation
        self.assertIsInstance(transBlock, Block)
        lbub = transBlock.lbub
        self.assertIsInstance(lbub, Set)
        self.assertEqual(lbub, ['lb', 'ub', 'eq'])

        disjBlock = transBlock.relaxedDisjuncts
        self.assertIsInstance(disjBlock, Block)
        self.assertEqual(len(disjBlock), 2)

    def test_transformation_block_name_collision(self):
        m = models.makeTwoTermDisj_Nonlinear()
        # add block with the name we are about to try to use
        m._pyomo_gdp_chull_relaxation = Block(Any)
        TransformationFactory('gdp.chull').apply_to(m)

        # check that we got a uniquely named block
        transBlock = m.component("_pyomo_gdp_chull_relaxation_4")
        self.assertIsInstance(transBlock, Block)

        # check that the relaxed disjuncts really are here.
        disjBlock = transBlock.relaxedDisjuncts
        self.assertIsInstance(disjBlock, Block)
        self.assertEqual(len(disjBlock), 2)
        self.assertIsInstance(disjBlock[0].component("d[0].c"), Constraint)
        self.assertIsInstance(disjBlock[1].component("d[1].c1"), Constraint)
        self.assertIsInstance(disjBlock[1].component("d[1].c2"), Constraint)

        # we didn't add to the block that wasn't ours
        self.assertEqual(len(m._pyomo_gdp_chull_relaxation), 0)

    def test_info_dict_name_collision(self):
        m = models.makeTwoTermDisj_Nonlinear()
        # we never have a way to know if the dictionary we made was ours. But we
        # should yell if there is a non-dictionary component of the same name.
        m._gdp_transformation_info = Block()
        self.assertRaisesRegexp(
            GDP_Error,
            "Component unknown contains an attribute named "
            "_gdp_transformation_info. The transformation requires that it can "
            "create this attribute!*",
            TransformationFactory('gdp.chull').apply_to,
            m)

    def test_indicator_vars_still_active(self):
        m = models.makeTwoTermDisj_Nonlinear()
        TransformationFactory('gdp.chull').apply_to(m)

        self.assertIsInstance(m.d[0].indicator_var, Var)
        self.assertTrue(m.d[0].indicator_var.active)
        self.assertTrue(m.d[0].indicator_var.is_binary())
        self.assertIsInstance(m.d[1].indicator_var, Var)
        self.assertTrue(m.d[1].indicator_var.active)
        self.assertTrue(m.d[1].indicator_var.is_binary())

    def test_disaggregated_vars(self):
        m = models.makeTwoTermDisj_Nonlinear()
        TransformationFactory('gdp.chull').apply_to(m)

        disjBlock = m._pyomo_gdp_chull_relaxation.relaxedDisjuncts
        # same on both disjuncts
        for i in [0,1]:
            relaxationBlock = disjBlock[i]
            w = relaxationBlock.w
            x = relaxationBlock.x
            y = relaxationBlock.y
            # variables created
            self.assertIsInstance(w, Var)
            self.assertIsInstance(x, Var)
            self.assertIsInstance(y, Var)
            # the are in reals
            self.assertIsInstance(w.domain, RealSet)
            self.assertIsInstance(x.domain, RealSet)
            self.assertIsInstance(y.domain, RealSet)
            # they don't have bounds
            self.assertEqual(w.lb, 0)
            self.assertEqual(w.ub, 7)
            self.assertEqual(x.lb, 0)
            self.assertEqual(x.ub, 8)
            self.assertEqual(y.lb, -10)
            self.assertEqual(y.ub, 0)

    def check_furman_et_al_denominator(self, expr, ind_var):
        self.assertEqual(expr._const, EPS)
        self.assertEqual(len(expr._args), 1)
        self.assertEqual(len(expr._coef), 1)
        self.assertEqual(expr._coef[0], 1 - EPS)
        self.assertIs(expr._args[0], ind_var)

    # TODO: Revise this test
    @unittest.expectedFailure
    def test_transformed_constraint_nonlinear(self):
        m = models.makeTwoTermDisj_Nonlinear()
        TransformationFactory('gdp.chull').apply_to(m)

        disjBlock = m._pyomo_gdp_chull_relaxation.relaxedDisjuncts

        # the only constraint on the first block is the non-linear one
        disj1c = disjBlock[0].component("d[0].c")
        self.assertIsInstance(disj1c, Constraint)
        # we only have an upper bound
        self.assertEqual(len(disj1c), 1)
        cons = disj1c['ub']
        self.assertIsNone(cons.lower)
        self.assertEqual(cons.upper, 0)
        repn = generate_standard_repn(cons.body)
        self.assertEqual(len(repn.linear_vars), 1)
        self.assertEqual(repn.linear_coefs[0], -14)
        # first term
        firstterm = cons.body._args[0]
        self.assertEqual(len(firstterm._numerator), 2)
        self.assertEqual(len(firstterm._denominator), 0)
        self.check_furman_et_al_denominator(firstterm._numerator[0],
                                       m.d[0].indicator_var)
        sub_part = firstterm._numerator[1]
        self.assertEqual(len(sub_part._coef), 2)
        self.assertEqual(len(sub_part._args), 2)
        self.assertEqual(sub_part._coef[0], 1)
        self.assertEqual(sub_part._coef[1], 1)
        x_part = sub_part._args[0]
        self.assertEqual(len(x_part._numerator), 1)
        self.assertIs(x_part._numerator[0], disjBlock[0].x)
        self.assertEqual(len(x_part._denominator), 1)
        self.check_furman_et_al_denominator(x_part._denominator[0],
                                            m.d[0].indicator_var)
        y_part = sub_part._args[1]
        self.assertEqual(len(y_part._args), 2)
        self.assertEqual(y_part._args[1], 2)
        y_frac = y_part._args[0]
        self.assertEqual(len(y_frac._numerator), 1)
        self.assertIs(y_frac._numerator[0], disjBlock[0].y)
        self.assertEqual(len(y_frac._denominator), 1)
        self.check_furman_et_al_denominator(y_frac._denominator[0],
                                            m.d[0].indicator_var)

        self.assertEqual(cons.body._coef[1], -1)
        secondterm = cons.body._args[1]
        self.assertEqual(len(secondterm._numerator), 2)
        self.assertEqual(len(secondterm._denominator), 0)
        self.assertEqual(secondterm._coef, EPS)
        h0 = secondterm._numerator[0]
        self.assertEqual(len(h0._args), 2)
        self.assertEqual(len(h0._coef), 2)
        self.assertEqual(h0._const, 0)
        self.assertEqual(len(h0._args[1]._args), 2)
        self.assertEqual(h0._args[0], 0)
        self.assertEqual(h0._args[1]._args[0], 0)
        self.assertEqual(h0._args[1]._args[1], 2)
        self.assertEqual(h0._coef[0], 1)
        self.assertEqual(h0._coef[1], 1)

        self.assertEqual(cons.body._coef[2], -14)
        thirdterm = cons.body._args[2]
        self.assertIs(thirdterm, m.d[0].indicator_var)

    def test_transformed_constraints_linear(self):
        m = models.makeTwoTermDisj_Nonlinear()
        TransformationFactory('gdp.chull').apply_to(m)

        disjBlock = m._pyomo_gdp_chull_relaxation.relaxedDisjuncts

        # the only constraint on the first block is the non-linear one
        c1 = disjBlock[1].component("d[1].c1")
        # has only lb
        self.assertEqual(len(c1), 1)
        cons = c1['lb']
        self.assertIsNone(cons.lower)
        self.assertEqual(cons.upper, 0)
        repn = generate_standard_repn(cons.body)
        self.assertEqual(len(repn.linear_vars), 2)
        self.assertIs(repn.linear_vars[0], m.d[1].indicator_var)
        self.assertIs(repn.linear_vars[1], disjBlock[1].x)
        self.assertEqual(repn.linear_coefs[0], 2)
        self.assertEqual(repn.linear_coefs[1], -1)

        c2 = disjBlock[1].component("d[1].c2")
        # 'eq' is preserved
        self.assertEqual(len(c2), 1)
        cons = c2['eq']
        self.assertEqual(cons.lower, 0)
        self.assertEqual(cons.upper, 0)
        repn = generate_standard_repn(cons.body)
        self.assertEqual(len(repn.linear_vars), 2)
        self.assertIs(repn.linear_vars[0], disjBlock[1].w)
        self.assertIs(repn.linear_vars[1], m.d[1].indicator_var)
        self.assertEqual(repn.linear_coefs[0], 1)
        self.assertEqual(repn.linear_coefs[1], -3)

        c3 = disjBlock[1].component("d[1].c3")
        # bounded inequality is split
        self.assertEqual(len(c3), 2)
        cons = c3['lb']
        self.assertIsNone(cons.lower)
        self.assertEqual(cons.upper, 0)
        repn = generate_standard_repn(cons.body)
        self.assertEqual(len(repn.linear_vars), 2)
        self.assertIs(repn.linear_vars[0], m.d[1].indicator_var)
        self.assertIs(repn.linear_vars[1], disjBlock[1].x)
        self.assertEqual(repn.linear_coefs[0], 1)
        self.assertEqual(repn.linear_coefs[1], -1)
        cons = c3['ub']
        self.assertIsNone(cons.lower)
        self.assertEqual(cons.upper, 0)
        repn = generate_standard_repn(cons.body)
        self.assertEqual(len(repn.linear_vars), 2)
        self.assertIs(repn.linear_vars[0], disjBlock[1].x)
        self.assertIs(repn.linear_vars[1], m.d[1].indicator_var)
        self.assertEqual(repn.linear_coefs[0], 1)
        self.assertEqual(repn.linear_coefs[1], -3)

    def check_bound_constraints(self, cons, disvar, indvar, lb, ub):
        self.assertIsInstance(cons, Constraint)
        # both lb and ub
        self.assertEqual(len(cons), 2)
        varlb = cons['lb']
        self.assertIsNone(varlb.lower)
        self.assertEqual(varlb.upper, 0)
        repn = generate_standard_repn(varlb.body)
        self.assertEqual(len(repn.linear_vars), 2)
        self.assertIs(repn.linear_vars[0], indvar)
        self.assertIs(repn.linear_vars[1], disvar)
        self.assertEqual(repn.linear_coefs[0], lb)
        self.assertEqual(repn.linear_coefs[1], -1)
        varub = cons['ub']
        self.assertIsNone(varub.lower)
        self.assertEqual(varub.upper, 0)
        repn = generate_standard_repn(varub.body)
        self.assertEqual(len(repn.linear_vars), 2)
        self.assertIs(repn.linear_vars[0], disvar)
        self.assertIs(repn.linear_vars[1], indvar)
        self.assertEqual(repn.linear_coefs[0], 1)
        self.assertEqual(repn.linear_coefs[1], -1*ub)

    def test_disaggregatedVar_bounds(self):
        m = models.makeTwoTermDisj_Nonlinear()
        TransformationFactory('gdp.chull').apply_to(m)

        disjBlock = m._pyomo_gdp_chull_relaxation.relaxedDisjuncts
        for i in [0,1]:
            # check bounds constraints for each variable on each of the two
            # disjuncts.
            self.check_bound_constraints(disjBlock[i].w_bounds, disjBlock[i].w,
                                         m.d[i].indicator_var, 2, 7)
            self.check_bound_constraints(disjBlock[i].x_bounds, disjBlock[i].x,
                                         m.d[i].indicator_var, 1, 8)
            self.check_bound_constraints(disjBlock[i].y_bounds, disjBlock[i].y,
                                         m.d[i].indicator_var, -10, -3)

    def test_xor_constraint(self):
        m = models.makeTwoTermDisj_Nonlinear()
        TransformationFactory('gdp.chull').apply_to(m)

        xorC = m._gdp_chull_relaxation_disjunction_xor
        self.assertIsInstance(xorC, Constraint)
        self.assertEqual(len(xorC), 1)

        self.assertEqual(xorC.lower, 1)
        self.assertEqual(xorC.upper, 1)
        repn = generate_standard_repn(xorC.body)
        self.assertEqual(repn.constant, 0)
        self.assertEqual(len(repn.linear_vars), 2)
        self.assertIs(repn.linear_vars[0], m.d[0].indicator_var)
        self.assertIs(repn.linear_vars[1], m.d[1].indicator_var)
        self.assertEqual(repn.linear_coefs[0], 1)
        self.assertEqual(repn.linear_coefs[1], 1)

    def test_error_for_or(self):
        m = models.makeTwoTermDisj_Nonlinear()
        m.disjunction.xor = False

        self.assertRaisesRegexp(
            GDP_Error,
            "Cannot do convex hull transformation for disjunction disjunction "
            "with or constraint. Must be an xor!*",
            TransformationFactory('gdp.chull').apply_to,
            m)

    def check_disaggregation_constraint(self, cons, var, disvar1, disvar2):
        self.assertEqual(cons.lower, 0)
        self.assertEqual(cons.upper, 0)
        repn = generate_standard_repn(cons.body)
        self.assertEqual(len(repn.linear_vars), 3)
        self.assertIs(repn.linear_vars[0], var)
        self.assertIs(repn.linear_vars[1], disvar1)
        self.assertIs(repn.linear_vars[2], disvar2)
        self.assertEqual(repn.linear_coefs[0], 1)
        self.assertEqual(repn.linear_coefs[1], -1)
        self.assertEqual(repn.linear_coefs[2], -1)

    def test_disaggregation_constraint(self):
        m = models.makeTwoTermDisj_Nonlinear()
        TransformationFactory('gdp.chull').apply_to(m)
        disjBlock = m._pyomo_gdp_chull_relaxation.relaxedDisjuncts

        disCons = m._gdp_chull_relaxation_disjunction_disaggregation
        self.assertIsInstance(disCons, Constraint)
        # one for each of the variables
        self.assertEqual(len(disCons), 3)
        self.check_disaggregation_constraint(disCons[2], m.w, disjBlock[0].w,
                                             disjBlock[1].w)
        self.check_disaggregation_constraint(disCons[0], m.x, disjBlock[0].x,
                                             disjBlock[1].x)
        self.check_disaggregation_constraint(disCons[1], m.y, disjBlock[0].y,
                                             disjBlock[1].y)

    def test_original_disjuncts_deactivated(self):
        m = models.makeTwoTermDisj_Nonlinear()
        TransformationFactory('gdp.chull').apply_to(m, targets=(m,))

        self.assertFalse(m.d.active)
        self.assertFalse(m.d[0].active)
        self.assertFalse(m.d[1].active)
        self.assertFalse(m.d[0].c.active)
        self.assertFalse(m.d[1].c1.active)
        self.assertFalse(m.d[1].c2.active)

    def test_transformed_disjunct_mappings(self):
        m = models.makeTwoTermDisj_Nonlinear()
        TransformationFactory('gdp.chull').apply_to(m)

        disjBlock = m._pyomo_gdp_chull_relaxation.relaxedDisjuncts

        # the disjuncts will always be transformed in the same order,
        # and d[0] goes first, so we can check in a loop.
        for i in [0,1]:
            infodict = disjBlock[i]._gdp_transformation_info
            self.assertIsInstance(infodict, dict)
            self.assertEqual(len(infodict), 4)
            self.assertIs(infodict['src'], m.d[i])
            self.assertIsInstance(infodict['srcConstraints'], ComponentMap)
            self.assertIsInstance(infodict['srcVars'], ComponentMap)
            self.assertIsInstance(
                infodict['boundConstraintToSrcVar'], ComponentMap)

            disjDict = m.d[i]._gdp_transformation_info
            self.assertIsInstance(disjDict, dict)
            self.assertEqual(sorted(iterkeys(disjDict)), ['chull','relaxed'])
            self.assertTrue(disjDict['relaxed'])
            self.assertIs(disjDict['chull']['relaxationBlock'], disjBlock[i])
            disaggregatedVars = disjDict['chull']['disaggregatedVars']
            self.assertIsInstance(disaggregatedVars, ComponentMap)
            bigmConstraints = disjDict['chull']['bigmConstraints']
            self.assertIsInstance(bigmConstraints, ComponentMap)
            relaxedConstraints = disjDict['chull']['relaxedConstraints']
            self.assertIsInstance(relaxedConstraints, ComponentMap)

    def test_transformed_constraint_mappings(self):
        m = models.makeTwoTermDisj_Nonlinear()
        TransformationFactory('gdp.chull').apply_to(m)

        disjBlock = m._pyomo_gdp_chull_relaxation.relaxedDisjuncts

        # first disjunct
        srcConsdict = disjBlock[0]._gdp_transformation_info['srcConstraints']
        transConsdict = m.d[0]._gdp_transformation_info['chull'][
            'relaxedConstraints']

        self.assertEqual(len(srcConsdict), 1)
        self.assertEqual(len(transConsdict), 1)
        orig1 = m.d[0].c
        trans1 = disjBlock[0].component("d[0].c")
        self.assertIs(srcConsdict[trans1], orig1)
        self.assertIs(transConsdict[orig1], trans1)

        # second disjunct
        srcConsdict = disjBlock[1]._gdp_transformation_info['srcConstraints']
        transConsdict = m.d[1]._gdp_transformation_info['chull'][
            'relaxedConstraints']

        self.assertEqual(len(srcConsdict), 3)
        self.assertEqual(len(transConsdict), 3)
        # first constraint
        orig1 = m.d[1].c1
        trans1 = disjBlock[1].component("d[1].c1")
        self.assertIs(srcConsdict[trans1], orig1)
        self.assertIs(transConsdict[orig1], trans1)
        # second constraint
        orig2 = m.d[1].c2
        trans2 = disjBlock[1].component("d[1].c2")
        self.assertIs(srcConsdict[trans2], orig2)
        self.assertIs(transConsdict[orig2], trans2)
        # third constraint
        orig3 = m.d[1].c3
        trans3 = disjBlock[1].component("d[1].c3")
        self.assertIs(srcConsdict[trans3], orig3)
        self.assertIs(transConsdict[orig3], trans3)

    def test_disaggregatedVar_mappings(self):
        m = models.makeTwoTermDisj_Nonlinear()
        TransformationFactory('gdp.chull').apply_to(m)

        disjBlock = m._pyomo_gdp_chull_relaxation.relaxedDisjuncts

        for i in [0,1]:
            srcVars = disjBlock[i]._gdp_transformation_info['srcVars']
            disVars = m.d[i]._gdp_transformation_info['chull'][
                'disaggregatedVars']
            self.assertEqual(len(srcVars), 3)
            self.assertEqual(len(disVars), 3)
            # TODO: there has got to be better syntax for this??
            mappings = ComponentMap()
            mappings[m.w] = disjBlock[i].w
            mappings[m.y] = disjBlock[i].y
            mappings[m.x] = disjBlock[i].x
            for orig, disagg in iteritems(mappings):
                self.assertIs(srcVars[disagg], orig)
                self.assertIs(disVars[orig], disagg)

    def test_bigMConstraint_mappings(self):
        m = models.makeTwoTermDisj_Nonlinear()
        TransformationFactory('gdp.chull').apply_to(m)

        disjBlock = m._pyomo_gdp_chull_relaxation.relaxedDisjuncts

        for i in [0,1]:
            srcBigm = disjBlock[i]._gdp_transformation_info[
                'boundConstraintToSrcVar']
            bigm = m.d[i]._gdp_transformation_info['chull']['bigmConstraints']
            self.assertEqual(len(srcBigm), 3)
            self.assertEqual(len(bigm), 3)
            # TODO: this too...
            mappings = ComponentMap()
            mappings[m.w] = disjBlock[i].w_bounds
            mappings[m.y] = disjBlock[i].y_bounds
            mappings[m.x] = disjBlock[i].x_bounds
            for var, cons in iteritems(mappings):
                self.assertIs(srcBigm[cons], var)
                self.assertIs(bigm[var], cons)

    def test_do_not_transform_user_deactivated_disjuncts(self):
        # TODO
        pass

    def test_unbounded_var_error(self):
        m = models.makeTwoTermDisj_Nonlinear()
        # no bounds
        m.w.setlb(None)
        m.w.setub(None)
        self.assertRaisesRegexp(
            GDP_Error,
            "Variables that appear in disjuncts must be "
            "bounded in order to use the chull "
            "transformation! Missing bound for w.*",
            TransformationFactory('gdp.chull').apply_to,
            m)

    def test_indexed_constraints_in_disjunct(self):
        m = models.makeThreeTermDisj_IndexedConstraints()

        TransformationFactory('gdp.chull').apply_to(m)
        transBlock = m._pyomo_gdp_chull_relaxation

        # 2 blocks: the original Disjunct and the transformation block
        self.assertEqual(
            len(list(m.component_objects(Block, descend_into=False))), 2)
        self.assertEqual(
            len(list(m.component_objects(Disjunct))), 0)

        # Each relaxed disjunct should have 3 vars, but i "d[i].c"
        # Constraints
        for i in [1,2,3]:
            relaxed = transBlock.relaxedDisjuncts[i-1]
            self.assertEqual(len(list(relaxed.component_objects(Var))), 3)
            self.assertEqual(len(list(relaxed.component_data_objects(Var))), 3)
            self.assertEqual(
                len(list(relaxed.component_objects(Constraint))), 4)
            # Note: m.x LB == 0, so only 3 bounds constriants (not 6)
            self.assertEqual(
                len(list(relaxed.component_data_objects(Constraint))), 3+i)
            self.assertEqual(len(relaxed.component('d[%s].c'%i)), i)

    def test_virtual_indexed_constraints_in_disjunct(self):
        m = ConcreteModel()
        m.I = [1,2,3]
        m.x = Var(m.I, bounds=(-1,10))
        def d_rule(d,j):
            m = d.model()
            d.c = Constraint(Any)
            for k in range(j):
                d.c[k+1] = m.x[k+1] >= k+1
        m.d = Disjunct(m.I, rule=d_rule)
        m.disjunction = Disjunction(expr=[m.d[i] for i in m.I])

        TransformationFactory('gdp.chull').apply_to(m)
        transBlock = m._pyomo_gdp_chull_relaxation

        # 2 blocks: the original Disjunct and the transformation block
        self.assertEqual(
            len(list(m.component_objects(Block, descend_into=False))), 2)
        self.assertEqual(
            len(list(m.component_objects(Disjunct))), 0)

        # Each relaxed disjunct should have 3 vars, but i "d[i].c"
        # Constraints
        for i in [1,2,3]:
            relaxed = transBlock.relaxedDisjuncts[i-1]
            self.assertEqual(len(list(relaxed.component_objects(Var))), 3)
            self.assertEqual(len(list(relaxed.component_data_objects(Var))), 3)
            self.assertEqual(
                len(list(relaxed.component_objects(Constraint))), 4)
            self.assertEqual(
                len(list(relaxed.component_data_objects(Constraint))), 3*2+i)
            self.assertEqual(len(relaxed.component('d[%s].c'%i)), i)


class IndexedDisjunction(unittest.TestCase):

    def test_disaggregation_constraints(self):
        m = models.makeTwoTermIndexedDisjunction()
        TransformationFactory('gdp.chull').apply_to(m)

        disaggregationCons = m._gdp_chull_relaxation_disjunction_disaggregation
        relaxedDisjuncts = m._pyomo_gdp_chull_relaxation.relaxedDisjuncts
        self.assertIsInstance(disaggregationCons, Constraint)
        self.assertEqual(len(disaggregationCons), 3)

        disaggregatedVars = {
            (1, 0): [relaxedDisjuncts[0].component('x[1]'),
                          relaxedDisjuncts[1].component('x[1]')],
            (2, 0): [relaxedDisjuncts[2].component('x[2]'),
                          relaxedDisjuncts[3].component('x[2]')],
            (3, 0): [relaxedDisjuncts[4].component('x[3]'),
                          relaxedDisjuncts[5].component('x[3]')],
        }

        for i, disVars in iteritems(disaggregatedVars):
            cons = disaggregationCons[i]
            self.assertEqual(cons.lower, 0)
            self.assertEqual(cons.upper, 0)
            repn = generate_standard_repn(cons.body)
            self.assertEqual(len(repn.linear_vars), 3)
            self.assertIs(repn.linear_vars[0], m.x[i[0]])
            self.assertIs(repn.linear_vars[1], disVars[0])
            self.assertIs(repn.linear_vars[2], disVars[1])
            self.assertEqual(repn.linear_coefs[0], 1)
            self.assertEqual(repn.linear_coefs[1], -1)
            self.assertEqual(repn.linear_coefs[2], -1)

    # TODO: also test disaggregation constraints for when we have a disjunction
    # where the indices are tuples. (This is to test that when we combine the
    # indices and the constraint name we get what we expect in both cases.)

class DisaggregatedVarNamingConflict(unittest.TestCase):
    @staticmethod
    def makeModel():
        m = ConcreteModel()
        m.b = Block()
        m.b.x = Var(bounds=(0, 10))
        m.add_component("b.x", Var(bounds=(-9, 9)))
        def disjunct_rule(d, i):
            m = d.model()
            if i:
                d.cons_block = Constraint(expr=m.b.x >= 5)
                d.cons_model = Constraint(expr=m.component("b.x")==0)
            else:
                d.cons_model = Constraint(expr=m.component("b.x") <= -5)
        m.disjunct = Disjunct([0,1], rule=disjunct_rule)
        m.disjunction = Disjunction(expr=[m.disjunct[0], m.disjunct[1]])

        return m

    def test_disaggregation_constraints(self):
        m = self.makeModel()
        TransformationFactory('gdp.chull').apply_to(m)

        disCons = m._gdp_chull_relaxation_disjunction_disaggregation
        self.assertIsInstance(disCons, Constraint)
        self.assertEqual(len(disCons), 2)
        # TODO: the above thing fails because the index gets overwritten. I
        # don't know how to keep them unique at the moment. When I do, I also
        # need to test that the indices are actually what we expect.

class NestedDisjunction(unittest.TestCase):

    def test_deactivated_disjunct_leaves_nested_disjuncts_active(self):
        m = models.makeNestedDisjunctions_FlatDisjuncts()
        m.d1.deactivate()
        # Specifying 'targets' prevents the HACK_GDP_Disjunct_Reclassifier
        # transformation of Disjuncts to Blocks
        TransformationFactory('gdp.chull').apply_to(m, targets=[m])

        self.assertFalse(m.d1.active)
        self.assertTrue(m.d1.indicator_var.fixed)
        self.assertEqual(m.d1.indicator_var.value, 0)

        self.assertFalse(m.d2.active)
        self.assertFalse(m.d2.indicator_var.fixed)

        self.assertTrue(m.d3.active)
        self.assertFalse(m.d3.indicator_var.fixed)

        self.assertTrue(m.d4.active)
        self.assertFalse(m.d4.indicator_var.fixed)

        m = models.makeNestedDisjunctions_NestedDisjuncts()
        m.d1.deactivate()
        # Specifying 'targets' prevents the HACK_GDP_Disjunct_Reclassifier
        # transformation of Disjuncts to Blocks
        TransformationFactory('gdp.chull').apply_to(m, targets=[m])

        self.assertFalse(m.d1.active)
        self.assertTrue(m.d1.indicator_var.fixed)
        self.assertEqual(m.d1.indicator_var.value, 0)

        self.assertFalse(m.d2.active)
        self.assertFalse(m.d2.indicator_var.fixed)

        self.assertTrue(m.d1.d3.active)
        self.assertFalse(m.d1.d3.indicator_var.fixed)

        self.assertTrue(m.d1.d4.active)
        self.assertFalse(m.d1.d4.indicator_var.fixed)

    @unittest.skipIf(not linear_solvers, "No linear solver available")
    def test_relaxation_feasibility(self):
        m = models.makeNestedDisjunctions_FlatDisjuncts()
        TransformationFactory('gdp.chull').apply_to(m)

        solver = SolverFactory(linear_solvers[0])

        cases = [
            (1,1,1,1,None),
            (0,0,0,0,None),
            (1,0,0,0,None),
            (0,1,0,0,1.1),
            (0,0,1,0,None),
            (0,0,0,1,None),
            (1,1,0,0,None),
            (1,0,1,0,1.2),
            (1,0,0,1,1.3),
            (1,0,1,1,None),
            ]
        for case in cases:
            m.d1.indicator_var.fix(case[0])
            m.d2.indicator_var.fix(case[1])
            m.d3.indicator_var.fix(case[2])
            m.d4.indicator_var.fix(case[3])
            results = solver.solve(m)
            if case[4] is None:
                self.assertEqual(results.solver.termination_condition,
                                 pyomo.opt.TerminationCondition.infeasible)
            else:
                self.assertEqual(results.solver.termination_condition,
                                 pyomo.opt.TerminationCondition.optimal)
                self.assertEqual(value(m.obj), case[4])

# TODO (based on coverage):

# test targets of all flavors
# test container deactivation
# test something with multiple indices


if __name__ == '__main__':
    unittest.main()

