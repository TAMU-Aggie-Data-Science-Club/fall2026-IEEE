import numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge


def fit_ridge(x, y, alpha=10.):
    model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
    return model.fit(np.asarray(x), np.asarray(y))
