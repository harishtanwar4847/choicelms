# -*- coding: utf-8 -*-
from setuptools import find_packages, setup

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

# get version from __version__ variable in lms/__init__.py
from lms import __version__ as version

setup(
    name="lms",
    version=version,
    description="Loan Managment System",
    author="Atrina Technologies Pvt. Ltd.",
    author_email="developers@atritechnocrat.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
