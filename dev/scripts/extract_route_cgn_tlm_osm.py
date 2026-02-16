# -*- coding: utf-8 -*-

import pandas as pd
import geopandas as gpd
from shapely import Polygon
import osmnx as ox

# Import des données géographiques
lng_min = 2490000
lng_max = 2570000
lat_min = 1110000
lat_max = 1160000
bbox = Polygon(((lng_min, lat_min), (lng_min, lat_max), (lng_max, lat_max), (lng_max, lat_min), (lng_min, lat_min)))
# Source des données : swissTOPO/swisstlmregio_2024_2056.shp/swissTLMRegio_Product_LV95/Transportation/swissTLMRegio_Ship.shp
gdf_ship = gpd.read_file(".../swisstlmregio_2024_2056.shp/swissTLMRegio_Product_LV95/Transportation/swissTLMRegio_Ship.shp", bbox=bbox)
# m = gdf_ship.explore(popup=True)
# m.save("gdf_ship.html")

crois = pd.read_csv("cgn_croisieres.csv", sep=";")
od = pd.read_csv("match_TLM_etapes.csv", sep=";")

gdf = gdf_ship[gdf_ship["OBJECTID"].isin(od["id_swissTLMRegio"])]
gdf["length"] = gdf["geometry"].length / 1000

df = pd.merge(od, gdf[["OBJECTID", "length"]], how="left", left_on="id_swissTLMRegio", right_on="OBJECTID")
df.drop(columns=["OBJECTID"], inplace=True)

# df.to_csv("length_TML.csv", sep=";", index=False)



################

# Source des données : swissTOPO/swisstlmregio_2024_2056.shp/swissTLMRegio_Product_LV95/Hydrography/swissTLMRegio_Lake.shp
gdf_lake = gpd.read_file(".../swisstlmregio_2024_2056.shp/swissTLMRegio_Product_LV95/Hydrography/swissTLMRegio_Lake.shp")
# m = gdf_lake.explore(popup=True)
# m.save("gdf_lake.html")

leman = gdf_lake[gdf_lake["OBJECTID"] == 1142].reset_index(drop=True).geometry[0]
leman_buff = leman.buffer(500)

data = {'shape': ['original', 'buffer'], 'geometry': [leman, leman_buff]}
gdf_buffer = gpd.GeoDataFrame(data, crs="EPSG:2056")

# m = gdf_buffer.explore(popup=True)
# m.save("gdf_buffer.html")

gdf_4326 = gdf_buffer.to_crs(4326)
leman_buff_4326 = gdf_4326[gdf_4326["shape"] == "buffer"].reset_index(drop=True).geometry[0]

tags = {"route": "ferry"}
gdf_osm = ox.features_from_polygon(leman_buff_4326, tags=tags).reset_index(drop=False)
gdf_osm = gdf_osm[['id', 'geometry', 'duration', 'name', 'network', 'operator']].reset_index(drop=True)

# m = gdf_osm.explore(popup=True)
# m.save("gdf_osm.html")

lines_osm = {
    "Yvoire - Saint-Prex": 163434889,
    "Coppet - Yvoire": 	963138897,
    "Lausanne - Vevey": 966014354,
    "Nernier - Yvoire": 967070340,
}
# "Nernier - Coppet" : indisponible -> backup via Yvoire

final_gdf = gdf_osm[gdf_osm["id"].isin(list(lines_osm.values()))]
final_gdf = final_gdf.to_crs(2056)
final_gdf["length"] = final_gdf["geometry"].length / 1000
final_gdf = final_gdf[['name', 'length']]

nernier_yvoire_km = final_gdf[final_gdf["name"] == "Nernier - Yvoire"].length.to_numpy()[0]
coppet_yvoire_km = final_gdf[final_gdf["name"] == "Coppet - Yvoire"].length.to_numpy()[0]
nernier_coppet_km = coppet_yvoire_km - nernier_yvoire_km

df1 = final_gdf[final_gdf["name"] != "Nernier - Yvoire"]
df2 = pd.DataFrame({"name": ["Nernier - Coppet"], "length": [nernier_coppet_km]})
final_osm = pd.concat([df1, df2], ignore_index=True)

# final_osm.to_csv("length_OSM.csv", sep=";", index=False)
