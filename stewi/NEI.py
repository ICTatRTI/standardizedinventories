#NEI import and process to Standardized EPA output format
#This script uses the NEI data exports from EIS.

import stewi.globals as globals
from stewi.globals import write_metadata
from stewi.globals import inventory_metadata
import pandas as pd
import numpy as np
import os
import time

report_year = '2011'

output_dir = globals.output_dir
data_dir = globals.data_dir
nei_required_fields = pd.read_table(data_dir + 'NEI_required_fields.csv',sep=',').fillna('Null')
nei_file_path = pd.read_table(data_dir + 'NEI_' + report_year + '_file_path.csv',sep=',').fillna('Null')

def read_data(source,file):
    tmp = pd.Series(list(nei_required_fields[source]), index=list(nei_required_fields['StandardizedEPA']))
    file_result = pd.DataFrame(columns=[x for x in tmp[tmp!='Null'].index if x!='FlowAmount']+['sum'])
    # read nei file by chunks
    for file_chunk in pd.read_table(file,sep=',',usecols=list(set(nei_required_fields[source])-set(['Null'])),chunksize=100000,engine='python'):
        # change column names to Standardized EPA names
        file_chunk = file_chunk.rename(columns=pd.Series(list(nei_required_fields['StandardizedEPA']),index=list(nei_required_fields[source])).to_dict())
        # aggregate
        file_chunk = file_chunk.groupby([x for x in tmp[tmp!='Null'].index if x!='FlowAmount'])['FlowAmount'].agg(['sum']).reset_index()
        # concatenate all chunks
        file_result = pd.concat([file_result,file_chunk])
    return file_result.groupby(file_result.columns[:-1].tolist())['sum'].agg(['sum']).reset_index()

def standardize_output(source): # source as 'Point'/'NonPoint'/'OnRoad'/'NonRoad'
    # extract file paths
    file_path = list(set(nei_file_path[source]) - set(['Null']))
    # read in first nei file by chunks
    nei = read_data(source,file_path[0])
    print(file_path[0])
    print(len(nei))
    # read in other nei files and concatenate all nei files into one dataframe
    for file in file_path[1:]:
        # concatenate all other files
        nei = pd.concat([nei,read_data(source,file)])
        # aggregate
        nei = nei.groupby(nei.columns[:-1].tolist())['sum'].agg(['sum']).reset_index()
        print(file)
        print(len(nei))
    # convert LB/TON to KG
    nei['FlowAmount'] = np.where(nei['UOM']=='LB',nei['sum']*0.453592,nei['sum']*907.184)
    # add not included standardized columns as empty columns
    nei = pd.concat([nei,pd.DataFrame(columns=list(set(nei_required_fields['StandardizedEPA']) - set(nei.columns)))])
    nei = nei.fillna('')
    # add Reliability Score
    if source == 'Point':
        reliability_table = pd.read_csv(data_dir + 'DQ_Reliability_Scores_Table3-3fromERGreport.csv',usecols=['Source','Code','DQI Reliability Score'])
        nei_reliability_table = reliability_table[reliability_table['Source'] == 'NEI']
        nei_reliability_table['Code'] = nei_reliability_table.Code.astype(float)
        nei = nei.merge(nei_reliability_table, left_on='ReliabilityScore', right_on='Code', how='left')
        nei['ReliabilityScore'] = nei['DQI Reliability Score']
        # drop Code and DQI Reliability Score columns
        nei = nei.drop(['Code', 'DQI Reliability Score'], 1)
    else:
        nei['ReliabilityScore'] = 3
    # add Source column
    nei['Source'] = source
    # drop UOM and sum columns
    nei = nei.drop(['UOM','sum'],1)
    return(nei)

def nei_aggregate_unit_to_facility_level(nei_):
    #drop zeroes from flow amount and reliability score
    nei_ = nei_[(nei_['FlowAmount'] > 0) & (nei_['ReliabilityScore'] > 0)]

    grouping_vars = ['FacilityID', 'FlowName']

    #Do groupby with sum of flow amount and weighted avg of reliabilty
    #Too slow right now
    # Define a lambda function to compute the weighted mean
    wm = lambda x: np.average(x, weights=nei_.loc[x.index, "FlowAmount"])
    # Define a dictionary with the functions to apply for a given column:
    f = {'FlowAmount': ['sum'], 'ReliabilityScore': {'weighted_mean': wm}}
    # Groupby and aggregate with your dictionary:
    neibyfacility = nei_.groupby(grouping_vars).agg(f)

    #Procedure without weighted avg for the groupby
    #neibyfacility = nei_point.groupby(grouping_vars)[['FlowAmount']]
    #neibyfacilityagg = neibyfacility.agg(sum)

    neibyfacility = neibyfacility.reset_index()
    neibyfacility.columns = neibyfacility.columns.droplevel(level=1)

    return(neibyfacility)

#NEIPoint
nei_point = standardize_output('Point')

#Pickle it
nei_point.to_pickle('NEI_' + report_year + '.pk')

##FlowByUnit output
nei_unit = nei_point.drop(columns=['FacilityName', 'CompanyName', 'Address', 'City', 'State',
                                   'Zip', 'Latitude', 'Longitude', 'NAICS', 'County','Source'])
nei_unit.to_csv(output_dir+'flowbyunit/'+'NEI_'+report_year+'.csv',index=False)
len(nei_unit)
#2016: 4103556
#2011: 3449947

#Flowbyfacility output
#re_idex nei_point
nei_point = nei_point.reset_index()
nei_flowbyfacility = nei_aggregate_unit_to_facility_level(nei_point)
nei_flowbyfacility.to_csv(output_dir+'NEI_'+report_year+'.csv',index=False)
len(nei_flowbyfacility)
#2016: 841735
#2011: 847136

##Flows output
#nei_flows = pd.DataFrame(pd.unique(nei_facility['FlowName','FlowID']),columns=['FlowName','FlowID'])
nei_flows = nei_point[['FlowName', 'FlowID']]
nei_flows = nei_flows.drop_duplicates()
nei_flows['Compartment']='air'
nei_flows['Unit']='kg'
nei_flows = nei_flows.sort_values(by='FlowName',axis=0)
nei_flows.to_csv(output_dir+'flow/'+'NEI_'+report_year+'.csv',index=False)
len(nei_flows)
#2016: 274
#2011: 273

##Facility output
facility = nei_point[['FacilityID', 'FacilityName', 'CompanyName', 'Address', 'City', 'State',
       'Zip', 'Latitude', 'Longitude', 'NAICS', 'County']]
facility = facility.drop_duplicates()
facility.to_csv(output_dir+'facility/'+'NEI_'+report_year+'.csv',index=False)
len(facility)
#2016: 48087
#2011: 55520

#Write metadata
NEI_meta = inventory_metadata

#Get time info from first point file
point_1_path = nei_file_path['Point'][0]
nei_retrieval_time = time.ctime(os.path.getctime(point_1_path))

if nei_retrieval_time is not None:
    NEI_meta['SourceAquisitionTime'] = nei_retrieval_time
NEI_meta['SourceFileName'] = point_1_path
NEI_meta['SourceURL'] = 'http://eis.epa.gov'

#extract version from filepath using regex
import re
pattern = 'V[0-9]'
version = re.search(pattern,point_1_path,flags=re.IGNORECASE)
if version is not None:
    NEI_meta['SourceVersion'] = version.group(0)

#Write metadata to json
write_metadata('NEI',report_year, NEI_meta)


#Needs a new format to output these data
#NEINonPoint
#nonpoint = standardize_output('NonPoint')
#NEIOnRoad
#onroad = standardize_output('OnRoad')
#NEINonRoad
#nonroad = standardize_output('NonRoad')
#nonpoint.to_csv(output_dir + 'NEINonPoint_2014.csv', index=False)
#onroad.to_csv(output_dir + 'NEIOnRoad_2014.csv', index=False)
#nonroad.to_csv(output_dir + 'NEINonRoad_2014.csv', index=False)
