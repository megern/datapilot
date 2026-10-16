"""Independent descriptive-statistics and numerical robustness tests."""
from fastapi.testclient import TestClient
from app.main import app
from app.core import ProfileRequest, analyze
client=TestClient(app,raise_server_exceptions=False)

def test_negative_correlation_and_sample_variance():
    r=analyze(ProfileRequest(rows=[{'x':1,'y':3},{'x':2,'y':2},{'x':3,'y':1}]))
    assert r['columns']['x']['stddev_sample']==1
    assert abs(r['correlations'][0]['pearson_r'] + 1) < 1e-12
    assert r['columns']['x']['q1']==1.5
    assert r['columns']['x']['q3']==2.5

def test_pairwise_missing_is_not_imputed():
    r=analyze(ProfileRequest(rows=[{'x':1,'y':None},{'x':None,'y':4},{'x':3,'y':6}]))
    assert r['correlations'][0]['paired_rows']==1
    assert r['correlations'][0]['pearson_r'] is None

def test_extreme_finite_values_return_diagnostic_or_rejection():
    response=client.post('/analyze',json={'rows':[{'x':-1e308,'y':1e308},{'x':1e308,'y':-1e308}]})
    assert response.status_code in (200,422)
