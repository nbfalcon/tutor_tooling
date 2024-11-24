#!/bin/env python3
import csv
from dataclasses import dataclass
import difflib
import glob
import os
import re
from sys import stderr
import pandas as pd


def user_error(message: str):
    print(message, file=stderr)
    exit(1)


def user_warning(message: str):
    print(message, file=stderr)


def in_submission_corr_folder_p():
    return os.path.basename(os.getcwd()).startswith("multi_feedback_") and os.path.isfile("status.csv")


def find_original_file(abspath_corr_folder: str):
    assert in_submission_corr_folder_p()
    cwd = os.getcwd()
    non_corr = os.path.join(os.path.dirname(cwd), os.path.basename(cwd).removeprefix("multi_feedback_"))
    assert os.path.isdir(non_corr)

    rel_to_corr = os.path.relpath(abspath_corr_folder)
    green_path = os.path.join("..", non_corr, rel_to_corr)
    assert os.path.isfile(green_path)

    return green_path


@dataclass
class SubmissionDir:
    name: str
    studon_id: str
    num_user_id: int

    abs_path: str

    @staticmethod
    def parse_dirname(dirname: str):
        *name_parts, studon_id, number = dirname.split("_")
        number = int(number)
        name = " ".join(name_parts)
        return SubmissionDir(name, studon_id, number, os.path.abspath(dirname))


def submission_files(sub: SubmissionDir):
    # FIXME: add scala here
    files = glob.glob(glob.escape(sub.abs_path) + "/**.java")
    files.sort()
    return files


def all_submissions():
    if not in_submission_corr_folder_p():
        user_error("Please run this command from a multi_feedback_<submission number 2.3> folder")

    files = os.listdir()
    submissions = [
        SubmissionDir.parse_dirname(dir) for dir in files if os.path.isdir(dir)
    ]
    submissions.sort(key=lambda s: s.name)
    return submissions


# We don't want the students to insert "+1" comments themselves to give themselves an infinite points glitch :)
def positive_diff(original_file_content: str, modified_file_content: str):
    diff = difflib.unified_diff(
        original_file_content.splitlines(), modified_file_content.splitlines()
    )
    changed_lines = [l.removeprefix("+") for l in diff if l.startswith("+")]
    return "\n".join(changed_lines)


@dataclass
class FeedbackLine:
    value: float
    full_comment: str


def analyze_tutor_feedback(tutor_lines: str):
    # print(tutor_lines)
    feedbacks = re.findall(
        r"(\/\/ ([+-]\d+(?:\.\d+)?)[: ].*$)", tutor_lines, flags=re.MULTILINE
    )
    feedback_lines = [
        FeedbackLine(float(value), full_comment) for full_comment, value in feedbacks
    ]

    # print(tutor_lines)
    COMMENT_comment_m = re.search(
        r"^// COMMENT .*$(\r?\n)?(?:^//.*$(\r?\n)?)*", tutor_lines, flags=re.MULTILINE
    )
    if COMMENT_comment_m:
        COMMENT_comment = COMMENT_comment_m.group(0)
        COMMENT_comment = "\n".join(
            line.removeprefix("//").lstrip() for line in COMMENT_comment.splitlines()
        )
        COMMENT_comment = COMMENT_comment.removeprefix("COMMENT")
        COMMENT_comment = COMMENT_comment.strip()
    else:
        COMMENT_comment = None

    return feedback_lines, COMMENT_comment


def sum_submission(sub: SubmissionDir):
    positive = []
    negative = []
    a_feedback = []
    any_comment = None
    for sub_corr_file in submission_files(sub):
        original = find_original_file(sub_corr_file)
        with open(sub_corr_file, "r") as corrected, open(
            original, "r"
        ) as original_content:
            tutor_lines = positive_diff(original_content.read(), corrected.read())
            (new_feedback, comment) = analyze_tutor_feedback(tutor_lines)
            if comment is not None:
                if any_comment is not None:
                    user_warning(f"Duplicate COMMENTs for {sub.name}")
                any_comment = comment

            new_negative = [f.value for f in new_feedback if f.value < 0]
            new_positive = [f.value for f in new_feedback if f.value > 0]

            positive += new_positive
            negative += new_negative
            a_feedback += new_feedback

    pos_sum = sum(positive)
    neg_sum = abs(sum(negative))

    print(f"{sub.name}: +{pos_sum} -{neg_sum}")
    for line in a_feedback:
        print("\t" + line.full_comment)
    if any_comment:
        print(any_comment)
    print()

    return pos_sum, any_comment


def _df_map_update(df: pd.DataFrame, key_column: str, value_column: str, mapping: dict, ty):
    """Update value_column with the keys from key_column (mapped through mapping)"""
    df[value_column] = df[key_column].map(mapping).fillna(df[value_column]).astype(ty)
def _df_key_set(df: pd.DataFrame, key_column, value_column, keys: set, value):
    """Set the value_column to value, if the key_column is in keys"""
    df.loc[df[key_column].isin(keys), value_column] = value

def sum_submissions():
    id2grade = {}
    id2comment = {}
    for sub in all_submissions():
        (grade, comment) = sum_submission(sub)
        id2grade[sub.num_user_id] = grade
        id2comment[sub.num_user_id] = comment

    file = "status.csv"
    old_df = pd.read_csv(file, quoting=csv.QUOTE_ALL, keep_default_na=False)
    _df_map_update(old_df, "usr_id", "mark", id2grade, float)
    _df_map_update(old_df, "usr_id", "notice", id2comment, str)
    _df_key_set(old_df, "usr_id", "status", id2grade.keys(), "passed")
    _df_key_set(old_df, "usr_id", "update", id2grade.keys(), 1)
    old_df.to_csv(file, quoting=csv.QUOTE_ALL, header=True, index=False)


if __name__ == "__main__":
    sum_submissions()
