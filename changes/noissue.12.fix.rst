Development: Fix issue with minimum-constraints-develop.txt that was causing
failure of make check_reqs because the package Levenshtein and
python-Levenshtein are required by safety and are not in that file.  Added the
minimum version constraint required by safety.
