import unittest

import numpy as np
from scipy.stats import norm
from scipy.special import expit
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn import datasets
from functools import partial

from pyinterpret.core.explanations import Interpretation
from pyinterpret.util import exceptions
from pyinterpret.tests.arg_parser import create_parser

class TestPartialDependence(unittest.TestCase):

    def setUp(self):
        args = create_parser().parse_args()
        debug = args.debug
        self.seed = args.seed
        self.n = args.n
        self.dim = args.dim
        self.features = [str(i) for i in range(self.dim)]
        self.X = norm.rvs(0, 1, size=(self.n, self.dim), random_state=self.seed)
        self.B = np.array([-10.1, 2.2, 6.1])
        self.y = np.dot(self.X, self.B)
        self.y_as_int = np.round(expit(self.y))
        self.y_as_string = np.array([str(i) for i in self.y_as_int])
        # example dataset for y = B.X
        # X = array([[ 1.62434536, -0.61175641, -0.52817175], ... [-0.15065961, -1.40002289, -1.30106608]])  (1000 * 3)
        # B = array([-10.1,   2.2,   6.1])
        # y = array([ -2.09736000e+01,  -1.29850618e+00,  -1.73511155e+01, ...]) (1000 * 1)
        # features = ['0', '1', '2']
        ##
        # Other output types:
        # y_as_int = array[ 0.,  0.,  0.,  0.,  1.,  1.,  0.,  0.,  0.,  1.,  1.,  1.,  1., ...]
        # y_as_string = array['0.0', '0.0', '0.0', '0.0', '1.0', '1.0', '0.0', '0.0', '0.0', ... ]


        # Another set of input
        # sample data
        self.sample_x = np.array([[-2, -1], [-1, -1], [-1, -2], [1, 1], [1, 2], [2, 1]])
        self.sample_y = np.array([-1, -1, -1, 1, 1, 1])
        self.sample_feature_name = [str(i) for i in range(self.sample_x.shape[1])]

        if debug:
            self.interpreter = Interpretation(log_level='DEBUG')
        else:
            self.interpreter = Interpretation() # default level is 'WARNING'
        self.interpreter.load_data(self.X, feature_names=self.features)

        self.regressor = LinearRegression()
        self.regressor.fit(self.X, self.y)
        self.regressor_predict_fn = self.regressor.predict

        self.classifier = LogisticRegression()
        self.classifier.fit(self.X, self.y_as_int)
        self.classifier_predict_fn = self.classifier.predict
        self.classifier_predict_proba_fn = self.classifier.predict_proba

        self.string_classifier = LogisticRegression()
        self.string_classifier.fit(self.X, self.y_as_string)


    @staticmethod
    def feature_column_name_formatter(columnname):
        return "val_{}".format(columnname)


    def test_pdp_with_default_sampling(self):
        pdp_df = self.interpreter.partial_dependence.partial_dependence([self.features[0]],
                                                                       self.regressor_predict_fn,
                                                                       sample=True)
        self.assertEquals(pdp_df.shape, (100, 3)) # default grid resolution is 100


    def test_partial_dependence_binary_classification(self):
        # In the default implementation of pdp on sklearn, there is an approx. done
        # if the number of unique values for a feature space < grid_resolution specified.
        # For now, we have decided to not have that approximation. In V2, we will be benchmarking for
        # performance as well. Around that time we will revisit the same.
        # Reference: https://github.com/scikit-learn/scikit-learn/blob/4d9a12d175a38f2bcb720389ad2213f71a3d7697/sklearn/ensemble/tests/test_partial_dependence.py
        # TODO: check on the feature space approximation (V2)
        # Test partial dependence for classifier
        clf = GradientBoostingClassifier(n_estimators=10, random_state=1)
        clf.fit(self.sample_x, self.sample_y)
        classifier_predict_fn = clf.predict_proba
        interpreter = Interpretation()
        interpreter.load_data(np.array(self.sample_x), self.sample_feature_name)
        pdp_df = interpreter.partial_dependence.partial_dependence(['0'], classifier_predict_fn,
                                                                  grid_resolution=5, sample=True)
        self.assertEquals(pdp_df.shape[0], 5)

        # now with our own grid
        ud_grid = np.unique(self.sample_x[:, 0])
        # input: array([-2, -1,  1,  2])
        # the returned grid should have only 4 values as specified by the user
        pdp_df = interpreter.partial_dependence.partial_dependence(['0'], classifier_predict_fn,
                                                                   grid=ud_grid, sample=True)
        self.assertEquals(pdp_df.shape[0], 4)


    def test_partial_dependence_multiclass(self):
        # Iris data classes: ['setosa', 'versicolor', 'virginica']
        iris = datasets.load_iris()
        #1. Using GB Classifier
        clf = GradientBoostingClassifier(n_estimators=10, random_state=1)
        clf.fit(iris.data, iris.target)
        classifier_predict_fn = clf.predict_proba
        interpreter = Interpretation()
        interpreter.load_data(iris.data, iris.feature_names)
        pdp_df = interpreter.partial_dependence.partial_dependence([iris.feature_names[0]], classifier_predict_fn,
                                                                   grid_resolution=25, sample=True)

        expected_feature_name = 'val_sepal length (cm)'
        self.assertEquals(expected_feature_name, pdp_df.columns[4])
        self.assertEquals(pdp_df.shape, (25, 5))

        #2. Using SVC
        from sklearn import svm
        # With SVC, predict_proba is supported only if probability flag is enabled, by default it is false
        clf = svm.SVC(probability=True)
        clf.fit(iris.data, iris.target)
        classifier_predict_fn = clf.predict_proba
        interpreter = Interpretation()
        interpreter.load_data(iris.data, iris.feature_names)
        pdp_df = interpreter.partial_dependence.partial_dependence([iris.feature_names[0]], classifier_predict_fn,
                                                                   grid_resolution=25, sample=True)
        self.assertEquals(expected_feature_name, pdp_df.columns[4])
        self.assertEquals(pdp_df.shape, (25, 5))



    def test_pdp_regression_coefs_are_close_1d(self, epsilon=1):
        coefs = self.interpreter.partial_dependence.partial_dependence([self.features[0]],
                                                                       self.regressor_predict_fn)
        val_col = self.feature_column_name_formatter(self.features[0])
        y = np.array(coefs['mean'])
        x = np.array(coefs[val_col])[:, np.newaxis]
        pdp_reg = LinearRegression()
        pdp_reg.fit(x, y)
        self.interpreter.logger.debug("PDP coefs: {}".format(pdp_reg.coef_))
        self.interpreter.logger.debug("PDP coef shape: {}".format(pdp_reg.coef_.shape))
        coef = pdp_reg.coef_[0]
        coefs_are_close_warning = "Lime coefficients for regressions model are not " \
                                  "close to true values for trivial case"
        coefs_are_close = abs(coef - self.B[0]) < epsilon
        if not coefs_are_close:
            coefs_are_close_warning += "True Coefs: {}".format(self.B[self.features[0]])
            coefs_are_close_warning += "Estimated Coefs: {}".format(coef)
            self.fail(coefs_are_close_warning)


    def test_2D_pdp(self):
        coefs = self.interpreter.partial_dependence.partial_dependence(self.features[:2],
                                                                       self.regressor_predict_fn,
                                                                       grid_resolution=10,
                                                                       sample=True)

    def test_plot_1D_pdp(self):
        coefs = self.interpreter.partial_dependence.plot_partial_dependence([self.features[0]],
                                                                       self.regressor_predict_fn,
                                                                       grid_resolution=10)


    def test_plot_1D_pdp_with_sampling(self):
        coefs = self.interpreter.partial_dependence.plot_partial_dependence(
            [self.features[0]],
            self.regressor_predict_fn,
            grid_resolution=10,
            sample=True
        )


    def test_plot_2D_pdp(self):
        coefs = self.interpreter.partial_dependence.plot_partial_dependence(self.features[:2],
                                                                       self.regressor_predict_fn,
                                                                       grid_resolution=10,
                                                                       sample=False)

    def test_plot_2D_pdp_with_sampling(self):
        coefs = self.interpreter.partial_dependence.plot_partial_dependence(self.features[:2],
                                                                       self.regressor_predict_fn,
                                                                       grid_resolution=10,
                                                                       sample=True)


    def test_fail_when_grid_range_is_outside_0_and_1(self):
        pdp_func = partial(self.interpreter.partial_dependence.partial_dependence,
                           *[[self.features[0]], self.regressor_predict_fn],
                           **{'grid_range':(.01, 1.01)})
        self.assertRaises(exceptions.MalformedGridRangeError, pdp_func)


    def test_pdp_1d_classifier_no_proba(self):
        coefs = self.interpreter.partial_dependence.partial_dependence(self.features[:1],
                                                                       self.classifier_predict_fn,
                                                                       grid_resolution=10)


    def test_pdp_2d_classifier_no_proba(self):
        coefs = self.interpreter.partial_dependence.partial_dependence(self.features[:2],
                                                                            self.classifier_predict_fn,
                                                                            grid_resolution=10)


    def test_pdp_1d_classifier_with_proba(self):
        coefs = self.interpreter.partial_dependence.partial_dependence(self.features[:1],
                                                                            self.classifier_predict_proba_fn,
                                                                            grid_resolution=10)


    def test_pdp_2d_classifier_with_proba(self):
        coefs = self.interpreter.partial_dependence.partial_dependence(self.features[:2],
                                                                            self.classifier_predict_proba_fn,
                                                                            grid_resolution=10)


    def test_pdp_1d_string_classifier_no_proba(self):
        coefs = self.interpreter.partial_dependence.partial_dependence(self.features[:1],
                                                                       self.string_classifier.predict,
                                                                       grid_resolution=10)


    def test_pdp_1d_string_classifier_with_proba(self):
        coefs = self.interpreter.partial_dependence.partial_dependence(self.features[:1],
                                                                       self.string_classifier.predict_proba,
                                                                       grid_resolution=10)


    #TODO: Add tests for various kinds of kwargs like sampling for pdp funcs
if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPartialDependence)
    unittest.TextTestRunner(verbosity=2).run(suite)