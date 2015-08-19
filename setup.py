from setuptools import setup, find_packages

setup(
    name='flightsearcher',
    description='Find good flights using QPX',
    #long_description=open('README.rst').read().strip(),
    version='0.0.1',
    author='Michael Axiak',
    author_email='mike@axiak.net',
    license='All Rights Reserved',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'flightsearcher = flightsearcher:main',
        ],
    },
    install_requires=[
        'requests==2.7.0',
        'certifi',
        'urllib3',
    ],
    classifiers=[],
)

