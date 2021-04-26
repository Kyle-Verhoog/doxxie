from setuptools import find_packages
from setuptools import setup


with open("README.md", "r") as f:
    long_description = f.read()


setup(
    name="doxxie",
    description="Uncover your mypy-typed library's true public API",
    url="https://github.com/Kyle-Verhoog/doxxie",
    author="Kyle Verhoog",
    author_email="kyle@verhoog.ca",
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="BSD 3",
    packages=find_packages(exclude=["tests*"]),
    package_data={"doxxie": ["py.typed"]},
    python_requires=">=3.6",
    install_requires=[
        "mypy",
    ],
    setup_requires=["setuptools_scm"],
    use_scm_version=True,
    entry_points={
        "console_scripts": [
            "doxxie=doxxie.stubgen:main",
        ]
    },
    # Required for mypy compatibility, see
    # https://mypy.readthedocs.io/en/stable/installed_packages.html#making-pep-561-compatible-packages
    zip_safe=False,
)
