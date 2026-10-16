from app.core import *

def test_numeric_missing_correlation():
    r=analyze(ProfileRequest(rows=[{'x':1,'y':2},{'x':2,'y':4},{'x':None,'y':6},{'x':3,'y':6}]))
    assert r['columns']['x']['mean']==2
    assert r['columns']['x']['missing_count']==1
    assert r['correlations'][0]['paired_rows']==3
    assert abs(r['correlations'][0]['pearson_r']-1)<1e-10

def test_outlier_and_constant():
    r=analyze(ProfileRequest(rows=[{'x':v,'y':1} for v in [1,2,3,4,100]]))
    assert r['columns']['x']['outlier_row_indices']==[4]
    assert r['correlations'][0]['pearson_r'] is None

def test_boolean_and_mixed():
    r=analyze(ProfileRequest(rows=[{'x':True,'z':None},{'x':'1'}]))
    assert r['columns']['x']['numeric_count']==0
    assert r['columns']['z']['type']=='empty'

def test_nonfinite_rejected():
    import pytest
    with pytest.raises(ValueError): ProfileRequest(rows=[{'x':float('nan')}])
