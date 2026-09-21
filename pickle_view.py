#!/usr/bin/env python

# Simple script to view contents of a cookie file stored in a pickle format

import pickle
import sys

if __name__ == '__main__':
    argv = sys.argv
    if len(argv) <= 1:
        print("Specify a pickle file as a parameter, e.g. cookies/user.pkl")
    else:
        try:
            with open(argv[1], "rb") as f:
                print(pickle.load(f))
        except (FileNotFoundError, PermissionError, pickle.UnpicklingError, EOFError) as e:
            print(f"Error loading pickle file: {e}")
