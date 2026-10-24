import math, numpy as np, pandas as pd, os
from xferbench.evaluation.evaluator import evaluate
from xferbench.scalable_eval.core import finalize, partial_sums_polars, partial_sums_spark
W={"E":0.5,"N":0.5}
def mk(actE, actN, fE, fN, statuses=None, dup=False):
    req=pd.DataFrame({"request_id":["r1","r2"],"scenario":["E","N"],"board":["b","b"],"ranked":[True,True],"category":["c","c"],"region":["x","x"],"fixture_kind":["n","n"]})
    t=[];f=[]
    for rid,acts,fs in (("r1",actE,fE),("r2",actN,fN)):
        for h,(a,fv) in enumerate(zip(acts,fs)):
            t.append(dict(request_id=rid,horizon_week=h,actual=a,measured=True))
            f.append(dict(method_id="m",variant_id="v",request_id=rid,horizon_week=h,point_units=fv,status="success",reason=""))
    f=pd.DataFrame(f)
    if statuses is not None: f["status"]=statuses
    if dup: f=pd.concat([f,f.iloc[[0]]],ignore_index=True)
    return f,pd.DataFrame(t),req
def cmp(name,args,spark=None):
    fc,t,r=args
    try: ref=evaluate(fc,t,r,W); 
    except Exception as e: ref=f"ERR {type(e).__name__}: {e}"
    out={}
    for eng in ["polars"]+(["spark"] if spark else []):
        try:
            if eng=="polars": g=finalize(*partial_sums_polars(fc,t,r),W)
            else:
                S=lambda d: spark.createDataFrame(d.to_dict("records"))
                g=finalize(*partial_sums_spark(S(fc[["method_id","variant_id","request_id","horizon_week","point_units","status"]]),S(t[["request_id","horizon_week","actual","measured"]]),S(r[["request_id","scenario","board"]])),W)
        except Exception as e: out[eng]=f"ERR {type(e).__name__}: {e}"; continue
        if isinstance(ref,str): out[eng]=("ref "+ref, g["b"][0]["objective"]); continue
        R=ref["boards"]["b"][0]; G=g["b"][0]; d=0; mism=[]
        for s in W:
            for k in ("WMAPE","Bias","coverage"):
                a,b=R["scenarios"][s][k],G["scenarios"][s][k]
                if (a is None)!=(b is None) or (a is not None and (math.isnan(b) or abs(a-b)>1e-9)): mism.append((s,k,a,b))
                elif a is not None: d=max(d,abs(a-b))
        a,b=R["objective"],G["objective"]
        if (a is None)!=(b is None) or (a is not None and not abs(a-b)<=1e-9): mism.append(("obj",a,b))
        elif a is not None: d=max(d,abs(a-b))
        out[eng]=("OK" if not mism else "MISMATCH", f"maxdiff={d:.3g}", mism)
    print(name, out)
rng=np.random.default_rng(0)
cases={
 "normal":mk([1,2,3],[4,5,6],[1.5,2,2],[3,5,9]),
 "all_zero_actual_E":mk([0,0,0],[4,5,6],[1,0,2],[3,5,9]),
 "large_1e15":mk([1e15,3e15,7e14],[2e15,1e15,5e14],[1.1e15,2.9e15,7.5e14],[2.1e15,0.9e15,6e14]),
 "large_1e300":mk([1e300,1e300],[1e300,1e300],[2e300,1e300],[1e300,1e300]),
 "random_1e5":mk(list(rng.poisson(50,50000).astype(float)),list(rng.poisson(5,50000).astype(float)),list(rng.normal(50,10,50000)),list(rng.normal(5,2,50000))),
 "nan_forecast":mk([1,2],[3,4],[np.nan,2],[3,4]),
 "inf_forecast":mk([1,2],[3,4],[np.inf,2],[3,4]),
 "failed_status":mk([1,2],[3,4],[1,2],[3,4],statuses=["failed","success","success","success"]),
 "duplicate_forecast_row":mk([1,2],[3,4],[1,2],[3,4],dup=True),
 "nan_actual":mk([np.nan,2],[3,4],[1,2],[3,4]),
 "negative_actual_sum":mk([-1,0],[3,4],[1,2],[3,4]),
}
fc,t,r=mk([1,2],[3,4],[1,2],[3,4]); cases["empty_group_N"]=(fc[fc.request_id=="r1"],t,r)
fc,t,r=mk([1,2],[3,4],[1,2],[3,4]); r2=r.copy(); r2.loc[1,"scenario"]="X"; cases["scenario_absent"]=(fc,t,r2)
fc,t,r=mk([1,2],[3,4],[1,2],[3,4]); f2=pd.concat([fc,fc.assign(method_id="m2")]); cases["two_methods_same_variant_id"]=(f2,t,r)
spark=None
if os.environ.get("SPARK"):
    os.environ.setdefault("SPARK_LOCAL_IP","127.0.0.1")
    from pyspark.sql import SparkSession
    spark=SparkSession.builder.master("local[2]").config("spark.ui.enabled","false").getOrCreate()
for k,v in cases.items(): cmp(k,v,spark)
fc,t,r=mk([1,2],[3,4],[1,2],[3,4]); f3=pd.concat([fc,fc.iloc[[0]]]).drop(index=1).reset_index(drop=True)
print("---"); cmp("dup_masks_missing",(f3,t,r))
fc,t,r=mk([np.nan,2],[3,4],[1,2],[3,4]); print(finalize(*partial_sums_polars(fc,t,r),W)["b"][0]["scenarios"]["E"])
