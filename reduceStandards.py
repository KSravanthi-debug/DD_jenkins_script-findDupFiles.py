"""Process and merge an excel spreadsheet exported from the development standards sharepoint
site.

The name of the exported excel spreadsheet is provided as the first argument. The name of the consolidated
master SS is provided as the second argument.

The program merges the first SS into the second by doing the following:

1.  Scanning the incoming SS column names for column names that contain values that shall be
    translated into numeric scores.
2.  Inserting a new column to the right of the valuable column.
3.  Iteratively scoring the incoming SS, putting the scored values into the adjacent column
4.  Writing the total score for the application (at the state represented by the SS) in the far right column
5.  Saving the updated SS as a new sheet in the second SS.
6.  Drawing a histogram and activity graph for the application's value.


TODO
1. Merge the output sheets into a single sheet per application that shows
Application name
Modified Date/time stamp of the data
The scores
The total score
The percentage
2. Single plot that summarizes each application's percentage in a histogram
3. One plot per application that shows progress over time.
4. Capture the SonarQube code stats(?)
5. Generate suggestion for quick wins i.e. what small imporvements results in large score gains.
   This is a function of marginal score increase * weight. So if for example the current score 
   for a specific behavior is say 0 and the next higher times the weight is 5 - that's a huge
   win to improve that specific score. Thee are sorted to porvide a recommendation.
"""
import pandas as pd
from pandas import ExcelWriter
from pandas import ExcelFile
from pandas import DataFrame
from collections import namedtuple

import sys
#import re
import time
import argparse
import logging

DEBUG = False
LOG_LEVEL = 'DEBUG'


def log(*msg: str) -> None:
    """ Simple logger
    """
    print(time.strftime("%Y-%m-%d %H:%M"), LOG_LEVEL, " ".join(map(str, msg)))

def bound_behavior(behavior: str) -> str:
    """ Associate behaviors that depend on another
    """
    bind_dict = {
        'SonarQube Quality Scanning': 'SonarQube Scan Review',
        'Fortify Security Scanning': 'Fortify Scan Review'
    }
    return bind_dict.get(behavior, None)

def wanted_col(column_value: str) -> namedtuple:
    """ Map a column with a value to be collected, to a tuple of:
        weight, max possible value, and expected values
    """
    Score = namedtuple('Score', 'weight maximum responses')

    switcher = {
        'Development Process': Score(1, 5, {
            'Yes - entirely': 5,
            'Yes - checkout, edit, build. No test and debug': 3,
            'No': 0,
            'N/A - binary distribution': None
        }),
        'Code Review': Score(2, 6, {
            'Yes - regularly scheduled process': 2,
            'Yes - ad hoc': 1,
            'Yes - peer review': 3,
            'Yes - pair programming': 3,
            'No': 0,
            'N/A - binary distribution': None
        }),
        'Source Code Control System': Score(2, 6, {
            'Github Appliance': 3,
            'Subversion': 1,
            'Not in source control': 0,
            'Binary distribution only': None
        }),
        'Jenkins Automated Build': Score(2, 10, {
            'Yes - continuous integration': 5,
            'Yes - on-demand': 3,
            'Yes - tagged deployment': 1,
            'No': 0,
            'N/A - binary distribution': None,
            'N/A - proprietray build system': 5
        }),
        'Unit Tests': Score(3, 6, {
            'None': 0,
            'Low coverage': 1,
            'High coverage': 2
        }),
        'SonarQube Quality Scanning': Score(2, 6, {
            'Yes - build job': 3,
            'Yes - developer action': 2,
            'No': 0,
            'N/A - binary distribution, no sources': None
        }),
        'SonarQube Scan Review': Score(2, 6, {
            'Yes - regularly': 3,
            'Yes - ad hoc': 2,
            'No': 0,
            'N/A - no scan': None,
            'N/A - binary distribution': None
        }),
        'Fortify Security Scanning': Score(2, 6, {
            'Yes - in a build': 3,
            'Yes - by a developer': 2,
            'No': 0,
            'N/A - binary distribution': None
        }),
        'Fortify Scan Review': Score(2, 6, {
            'Yes - regularly': 3,
            'Yes - regualrly': 3,
            'Yes - ad hoc': 2,
            'No': 0,
            'N/A - no scan': None,
            'N/A - binary distribution': None
        }),
        'Automated Testing': Score(5, 5, {
            'Yes': 1,
            'No': 0
        }),
        'Artifact Storage': Score(6, 6, {
            'Yes': 1,
            'No': 0
        }),
        'Deployment Automation (DEV)': Score(5, 5, {
            'Yes': 1,
            'No': 0
        }),
        'Deployment Automation (PROD)': Score(5, 5, {
            'Yes': 1,
            'No': 0
        })
    }
    score = switcher.get(column_value, None)  # throws KeyError or None?
    return score

def marginal_improvement(current_score: int, score: namedtuple, bound_column: str) -> namedtuple:
    """ Given the score and behavior and a potential bound column, return a tuple of the name and value of the next higher 
        behavior
    """
    ImprovedScore = namedtuple('ImprovedScore', 'wanted_behavior incremental_value')
    responses = score.responses
    sorted_responses = sorted(responses.items(), key=lambda kv: kv[1] if kv[1] != None else 0, reverse=True)
    i = 0
    for response_tuple in sorted_responses:
        if response_tuple[1] == current_score:
            if i == 0:
                return False  # No improvement to be had
            else:
                break
        i += 1
        wanted_tuple = response_tuple                # Hold back the last one for the next match
    # The response tuple should have the higher value we want to aim for.
    print(wanted_tuple)
    # TODO There is another column that comes into play - what does this do to the overall percentage calculation?
    if bound_column:
        pass
    # Return the marginal score improvement for implementing the named behavior
    return ImprovedScore(wanted_tuple[0], (wanted_tuple[1] - current_score) * score.weight) 

# Find the key with the value

def main(df: DataFrame) -> bool:
    """ Main program
    """
    if DEBUG:
        logging.debug('Shape: Records: ',
                      df.shape[0], 'Columns: ', df.shape[1])
        logging.debug('Columns headings', df.columns)

    if DEBUG:
        logging.debug(list(df))

    if DEBUG:
        logging.debug(pd)
        logging.debug(df.shape)

    col_wanted_list = []  # Optimization, wanted column lookaside
    # TODO keep overall stats?
    # Iterate for every row
    for i in range(df.shape[0]):
        row = df.iloc[i]
        # For every column
        total_score = 0
        maximum_score = 0
        for j in range(df.shape[1]):
            if i != 0 and j not in col_wanted_list:
                continue
            if DEBUG:
                logging.debug(row.index[j])
            if not isinstance(row[j], int) and not isinstance(row[j], str):
                continue
            score = wanted_col(row.index[j])
            # For the named columns - assign a value to the score, multiply by the weight
            if score:
                if i == 0:
                    col_wanted_list.append(j)
                # save the score and the weight
                weight = score.weight
                maximum = score.maximum
                score_map = score.responses
                if DEBUG:
                    logging.debug('Score map:', score_map[row[j]])
                if isinstance(score_map[row[j]], int):
                    # To do add a new SS?
                    score_value = weight * score_map[row[j]]     # Weighted value
                    df.loc[df.index[i], row.index[j] + ' Score'] = score_value
                    total_score += score_value
                    maximum_score += maximum
                    # Calculate the marginal score improvement by implementing the next higher behavior
                    # What if this has a side effect of dragging in a NA -> 0 for a correspondent score?
                    improved_score_tuple = marginal_improvement(score_map[row[j]], score, bound_behavior(row.index[j]))
                    if improved_score_tuple:
                        df.loc[df.index[i], row.index[j] + ' Improvement'] = improved_score_tuple.wanted_behavior
                        df.loc[df.index[i], row.index[j] + ' Improvement Score'] = improved_score_tuple.incremental_value
                else:
                    if DEBUG:
                        logging.debug('Column name:', row.index[j], score_map[row[j]],
                                      ' not an int - not counted')
        df.loc[df.index[i], 'Total Score'] = total_score
        df.loc[df.index[i], 'Maximum Score'] = maximum_score
        df.loc[df.index[i], 'Percentage'] = total_score * 100 // maximum_score
        if DEBUG:
            log(row)
    return True


def read_in(file_name: str, sheet_name: str) -> DataFrame:
    """ Read the input excel file into a dataframe
    """
    try:
        xl = pd.ExcelFile(file_name)
        return xl.parse(sheet_name)  # read the sheet into a DataFrame
    except FileNotFoundError as fnfe:
        logging.exception('Exception occured')
        logging.info('Unable to read input file: ' + file_name)
        raise fnfe


def write_file(file_name: str, sheet_name: str, data_frame: DataFrame) -> bool:
    """ Write a new SS file containing the df
    """
    rc = True
    try:
        writer = pd.ExcelWriter(file_name, engine='xlsxwriter')
        data_frame.to_excel(writer, sheet_name)
        writer.save()
    except PermissionError as pe:
        logging.exception('Exception occured')
        logging.info('Unable to write to output file: ' +
                     file_name + ' sheet: ' + sheet_name)
        rc = False
    return rc


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("in_file_name", help="the input excel file name from the share point site",
                        type=str)
    parser.add_argument("in_sheet_name", help="the input excel sheet name from the share point site",
                        type=str)
    parser.add_argument("out_file_name", help="the output excel file name to write",
                        type=str)
    parser.add_argument("out_sheet_name", help="the output excel file sheet name to write",
                        type=str)
    parser.add_argument("--debug", help="debug on", action="store_true")
    args = parser.parse_args()
    if args.debug:
        DEBUG = True
        logging.basicConfig(level=logging.DEBUG)
        logging.basicConfig(format='%(process)d-%(levelname)s-%(message)s')
    df = read_in(args.in_file_name, args.in_sheet_name)
    main(df)
    if write_file(args.out_file_name, args.out_sheet_name, df):
        sys.exit(0)
    else:
        sys.exit(6)
