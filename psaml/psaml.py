#
# Iris Analysis
#
from pyspark import SparkContext
from pyspark.ml import Model
from pyspark.ml import Pipeline
from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml.feature import VectorAssembler, StringIndexer, VectorIndexer
from pyspark.ml.regression import DecisionTreeRegressor
from pyspark.sql import *


# Helper: create data_info DataFrame from sample data (work item #5)
def make_data_info(sql, sample_data, cols_analyze, col_class):
    "create the data_info DataFrame the analysis function needs from sample data"    
    #  start by ignoring the class column
    vars_only = sample_data.drop(col_class)
    #  identify the mix and max for each column
    sample_data_info = vars_only.describe().collect()
    min_row = sample_data_info[3]
    max_row = sample_data_info[4]
    #  create schema for our final DataFrame, one Row at a time
    sample_row = Row("colName", "minValue", "maxValue", "shouldAnalyze")
    #  build Python list of Rows of column names and their metadata
    sample_list = []
    cols_analyze_set = set(cols_analyze)
    idx = 1
    for col in vars_only.columns:
        should = (col in cols_analyze_set)
        sample_list.append( sample_row( col, float(min_row[idx]), float(max_row[idx]), should ) )
        idx = idx + 1
    #  create the DataFrame and ship it back
    return sql.createDataFrame(sample_list)
    

# 1b) Generate test data (work item #4)
def generate_analysis_data(sql, exp_sensitivity, ctrl_sensitivity, data_info):
    "build the test data from the prepped cols_* DataFrames which should make it easy"
    #  gather the cols to analyze first!
    exp_cols = data_info.where(data_info.shouldAnalyze==True).collect()
    all_cols = data_info.collect()
    col_names = []
    for r in all_cols:
        col_names.append(r.colName)
    #  gather the min/max values once for efficiency
    mins = {}
    maxs = {}
    for col in col_names:
        colrow = data_info.where(data_info.colName==col).first()
        mins[col] = colrow.minValue
        maxs[col] = colrow.maxValue
    test_list = []
    #  for all values to hold control variables at...
    for c in range(0, ctrl_sensitivity+1):
        #  for each variable we want to analyze...
        for exp_var in exp_cols: 
            #  for all values to hold focus variable to...
            for e in range(0, exp_sensitivity+1):
                #  test_row = Row(col_names)
                test_vals = []
                #  for each value to be found within a Row of our output DataFrame...
                for col in col_names:
                    #  get min and max values for the variable in question
                    min = mins[col]
                    max = maxs[col]
                    #  set multiplicative variables to exp or ctrl var 
                    factor = float(c)
                    factorMax = float(ctrl_sensitivity)
                    if exp_var.colName == col:
                        factor = float(e)
                        factorMax = float(exp_sensitivity)
                    #  hard-wiring factorMax to 1 so that a 0 results in values only analyzed at 0% of possible value range
                    if factorMax == 0:
                        factorMax = float(1)
                    test_vals.append( min + ((max - min) * (factor / factorMax)) )
                test_list.append(test_vals)
    #  bundle all of this into a single DataFrame and ship it back!
    test_data = sql.createDataFrame(test_list, schema=col_names)
    return test_data


    #  DataFrame.count() gives me number of rows (useful for looping)
    #  DataFrame.collect() gives me a list of Rows 
    #  Row members can be accessed by name, Row.colName, Row.minValue, etc
    #  DataFrame.foreach(f) runs the f function on each Row of the DataFrame
    #  DataFrame.printSchema() gives string of ASCII tree representing DataFrame, may be useful for doing input validation human-legible
    #  DataFrame.schema() gives types within DataFrame, useful for asserting valid DataFrame format    
    #  DataFrame.select(cols) gives a new DataFrame limited to the provided columns
    #  DataFrame.selectExpr()
    #  DataFrame.take(n) return the first n Rows as a list of Rows
    #  DataFrame.where() is an alias for .filter() which takes string conditions to filter Rows

def do_continuous_input_analysis(sc, model, exp_sensitivity, ctrl_sensitivity, data_info):
    # ##########################################################################################################
    #
    # 0) Verify input
    #
    #  assert exp_sensitivity >= 0 (int)
    #  assert ctrl_sensitivity >= 0 (int)
    #  assert data_info (DataFrame of the following format, one row for each column in the data model works on):
    #
    #                                         DataFrame of Data columns
    #                     _____________________________________________________
    # Column purpose     | colName   | minValue  | maxValue  | shouldAnalyze   |
    #                    |-----------|-----------|-----------|-----------------|
    # Column type        | string    | numeral   | numeral   | boolean         |
    #                    |-----------|-----------|-----------|-----------------|
    # Example record     | "petalW"  | 4.3       | 7.9       | true            |
    #                    |___________|___________|___________|_________________|
    #
    try:
        assert (exp_sensitivity >= 0), "Experiment Sensitivity must be a non-negative integer"
        assert (ctrl_sensitivity >= 0), "Control Variable Sensitivity must be a non-negative integer"
    except AssertionError as e:
        raise ValueError(e.args)

    try:
        assert (type(sc) is SparkContext), "Invalid SparkContext"
        assert (isinstance(model, Model)), "Invalid ML Model; Model given: {0}".format(str(type(model)))
        assert (type(data_info) is DataFrame), "data_info is not a valid DataFrame"
    except AssertionError as e:
        raise TypeError(e.args)

    # This will be uncommented once we get the Test Data generation fixed, and start analyzing it instead
    # of the sample data we were submitting. Calling this issue done.
    #try:
    #    assert (len(data_info.columns) == 4), \
    #        "data_info is invalid; Len should be 4 instead of {0}".format(len(data_info.columns))
    #    assert (set(data_info.columns) == {'colName', 'minValue', 'maxValue', 'shouldAnalyze'}), \
    #        "data_info is invalid; Contains incorrect columns"
    #except AssertionError as e:
    #    raise RuntimeError(e.args)

    # 0.5) create SQLContext
    sql_context = SQLContext(sc)

    # ##########################################################################################################
    #
    # 1) Generate test data
    #

    #  test_data = generate_analysis_data(sql_context, exp_sensitivity, ctrl_sensitivity, data_info)

    # ##########################################################################################################
    #
    # 2) Make predictions.
    #
    # predictions = model.transform(testData)  #  but, we're not passing in data_info yet, so we'll treat
    # data_info like already done testData
    predictions = model.transform(data_info)

    # ##########################################################################################################
    #
    # 3) Transform predictions into output DataFrame
    #
    #  Output DataFrame should use the following format:
    #
    #                                            DataFrame name
    #                     _______________________________________________________________
    # Column purpose     | prediction   | varColName   | expVariance   | ctrlVariance    |
    #                    |--------------|--------------|---------------|-----------------|
    # Column types       | <classType>  | string       | num (0.0-1.0) | num (0.0-1.0)   |
    #                    |--------------|--------------|---------------|-----------------|
    # Example record     | "iris-setosa"| "PetalW"     | 0.7           | 0.2             |
    #                    |______________|______________|_______________|_________________|
    #
    # In the above example record, we get "iris-setosa" as a prediction when holding "PetalW" at 70% of potential
    # value, and everything else at 20%
    #
    #     varianceData = new DataFrame after above format
    #     for ( x : 0 ... ctrlSensitivity ), inclusive
    #        foreach ( varCol : varCol.shouldAnalyze == true )
    #           for ( y : 0 ... expSensitivity ), inclusive
    #              translate row from predictions[n] to  varianceData[n]
    #              #  they will end up being the same size
    #

    # return varianceData  # but for now, just return predictions so the code actually interprets
    return predictions
