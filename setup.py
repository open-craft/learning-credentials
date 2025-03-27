#!/usr/bin/env python
"""Package metadata for learning_credentials."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from setuptools import find_packages, setup


def get_version(file_path: Path) -> str:
    """
    Extract the version string from the file.

    Input:
     - file_paths: relative path fragments to file with
                   version string
    """
    filename = Path(__file__).parent / file_path
    with Path(filename).open(encoding="utf8") as f:
        version_file = f.read()
        version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", version_file, re.MULTILINE)
    if version_match:
        return version_match.group(1)
    raise RuntimeError('Unable to find version string.')  # noqa: EM101


def load_requirements(*requirements_paths: Path) -> list[str]:  # noqa: C901
    """
    Load all requirements from the specified requirements files.

    Requirements will include any constraints from files specified
    with -c in the requirements files.
    Returns a list of requirement strings.
    """
    # e.g. {"django": "Django", "confluent-kafka": "confluent_kafka[avro]"}
    by_canonical_name = {}

    def check_name_consistent(package: str) -> None:
        """
        Raise exception if package is named different ways.

        This ensures that packages are named consistently so we can match
        constraints to packages. It also ensures that if we require a package
        with extras we don't constrain it without mentioning the extras (since
        that too would interfere with matching constraints.)
        """
        canonical = package.lower().replace('_', '-').split('[')[0]
        seen_spelling = by_canonical_name.get(canonical)
        if seen_spelling is None:
            by_canonical_name[canonical] = package
        elif seen_spelling != package:
            raise Exception(  # noqa: TRY002
                f'Encountered both "{seen_spelling}" and "{package}" in requirements '  # noqa: EM102
                'and constraints files; please use just one or the other.',
            )

    requirements = {}
    constraint_files = set()

    # groups "pkg<=x.y.z,..." into ("pkg", "<=x.y.z,...")
    re_package_name_base_chars = r"a-zA-Z0-9\-_."  # chars allowed in base package name
    # Two groups: name[maybe,extras], and optionally a constraint
    requirement_line_regex = re.compile(
        fr"([{re_package_name_base_chars}]+(?:\[[{re_package_name_base_chars},\s]+])?)([<>=][^#\s]+)?",
    )

    def add_version_constraint_or_raise(
        current_line: str,
        current_requirements: dict[str, str],
        add_if_not_present: bool,  # noqa: FBT001
    ):
        regex_match = requirement_line_regex.match(current_line)
        if regex_match:
            package = regex_match.group(1)
            version_constraints = regex_match.group(2)
            check_name_consistent(package)
            existing_version_constraints = current_requirements.get(package)
            # It's fine to add constraints to an unconstrained package,
            # but raise an error if there are already constraints in place.
            if existing_version_constraints and existing_version_constraints != version_constraints:
                # noinspection PyExceptionInherit
                raise BaseException(  # noqa: TRY002
                    f'Multiple constraint definitions found for {package}:'  # noqa: EM102
                    f' "{existing_version_constraints}" and "{version_constraints}".'
                    f'Combine constraints into one location with {package}'
                    f'{existing_version_constraints},{version_constraints}.',
                )
            if add_if_not_present or package in current_requirements:
                current_requirements[package] = version_constraints

    # Read requirements from .in files and store the path to any
    # constraint files that are pulled in.
    for path in requirements_paths:
        with path.open() as reqs:
            for line in reqs:
                if is_requirement(line):
                    add_version_constraint_or_raise(line, requirements, add_if_not_present=True)
                if line and line.startswith('-c') and not line.startswith('-c http'):
                    constraint_files.add(path.parent / line.split('#')[0].replace('-c', '').strip())

    # process constraint files: add constraints to existing requirements
    for constraint_file in constraint_files:
        with constraint_file.open() as reader:
            for line in reader:
                if is_requirement(line):
                    add_version_constraint_or_raise(line, requirements, add_if_not_present=False)

    # process back into list of pkg><=constraints strings
    return [f'{pkg}{version or ""}' for (pkg, version) in sorted(requirements.items())]


def is_requirement(line: str) -> bool:
    """
    Return True if the requirement line is a package requirement.

    Returns:
        bool: True if the line is not blank, a comment, a URL, or an included file.
    """
    return bool(line and line.strip() and not line.startswith(("-r", "#", "-e", "git+", "-c")))


VERSION = get_version(Path('learning_credentials/__init__.py'))

if sys.argv[-1] == 'tag':
    print("Tagging the version on github:")  # noqa: T201
    os.system(f"git tag -a {VERSION} -m 'version {VERSION}'")  # noqa: S605
    os.system("git push --tags")  # noqa: S605, S607
    sys.exit()

README = (Path(__file__).parent / 'README.rst').open(encoding="utf8").read()
CHANGELOG = (Path(__file__).parent / 'CHANGELOG.rst').open(encoding="utf8").read()

setup(
    name='learning-credentials',
    version=VERSION,
    description="""A pluggable service for preparing Open edX credentials.""",
    long_description=README + '\n\n' + CHANGELOG,
    long_description_content_type='text/x-rst',
    author='OpenCraft',
    author_email='help@opencraft.com',
    url='https://github.com/open-craft/learning-credentials',
    packages=find_packages(
        include=['learning_credentials', 'learning_credentials.*', 'openedx_certificates', 'openedx_certificates.*'],
        exclude=["*tests"],
    ),
    entry_points={
        "lms.djangoapp": [
            "learning_credentials = learning_credentials.apps:LearningCredentialsConfig",
            "openedx_certificates = openedx_certificates.apps:OpenEdxCertificatesConfig",
        ],
    },
    include_package_data=True,
    install_requires=load_requirements(Path('requirements/base.in')),
    options={'bdist_wheel': {'universal': True}},
    python_requires=">=3.11",
    license="AGPL 3.0",
    zip_safe=False,
    keywords='Python edx',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Framework :: Django',
        'Framework :: Django :: 4.2',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],
)
