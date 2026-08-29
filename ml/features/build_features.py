"""Reusable baseline feature engineering for ThermoIntel observations."""
from math import radians, sin, cos, asin, sqrt

def distance_km(lat1, lon1, lat2, lon2):
    r=6371; p1,p2=radians(lat1),radians(lat2); dp=radians(lat2-lat1); dl=radians(lon2-lon1)
    a=sin(dp/2)**2+cos(p1)*cos(p2)*sin(dl/2)**2
    return 2*r*asin(sqrt(a))

def build_features(observation, nearest_facility=None, history=None):
    history=history or []
    frps=[float(item.get("frp",0)) for item in history if item.get("frp") is not None]
    mean=sum(frps)/len(frps) if frps else float(observation.get("frp",0))
    std=(sum((x-mean)**2 for x in frps)/len(frps))**.5 if frps else 0
    distance=distance_km(observation["latitude"],observation["longitude"],nearest_facility["latitude"],nearest_facility["longitude"]) if nearest_facility else None
    return {"frp":float(observation.get("frp",0)),"confidence":float(observation.get("confidence",0)),"distance_to_facility_km":distance,"detections_30d":len(frps),"historical_mean_frp":mean,"historical_std_frp":std,"baseline_z_score":(float(observation.get("frp",0))-mean)/(std or 1)}