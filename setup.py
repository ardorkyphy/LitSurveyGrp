import setuptools

description = "Open literature survey automation for paper discovery, scholarly metadata enrichment, accessible PDF collection, research-topic grouping, cited-reference analysis, statistics, and offline dashboards."

with open("README.md", "r", encoding="utf-8") as readme:
    long_description = readme.read()

setuptools.setup(
    name="litsurveygrp",
    version='0.1.0a0',
    author='Dingqi Zhang',
    author_email='zhangdingqi1998@gmail.com',
    description=description,
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/DQ-Zhang/LitSurveyGrp.git',
    packages=setuptools.find_packages(),
    install_requires=[
        "beautifulsoup4>=4.12",
        "pypdf>=4.0",
        "requests>=2.31",
        "scikit-learn>=1.3",
        "sentence-transformers>=2.2",
    ],
    extras_require={
        "pdf": ["PyMuPDF>=1.23"],
        "dev": ["pytest>=8.0"],
    },
    entry_points={
        "console_scripts": [
            "lsg=litsurveygrp.__main__:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Healthcare Industry",
        "Intended Audience :: Education",
        "Topic :: Scientific/Engineering",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows"
    ],
    python_requires='>=3.10'
)
