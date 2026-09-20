from os import path

import setuptools
import re


def read(fname):
    with open(path.join(path.dirname(__file__), fname), encoding="utf-8") as f:
        return f.read()


metadata = dict(
    re.findall(
        r"""__([a-z]+)__ = "([^"]+)""", read("TwitchChannelPointsMiner/__init__.py")
    )
)

setuptools.setup(
    name="Twitch-Channel-Points-Miner-v2",
    version=metadata["version"],
    author="Tkd-Alex (Alessandro Maggio), rdavydov (Roman Davydov), krabhi4",
    author_email="kabhi87654@gmail.com",
    description="A simple script that will watch a stream for you and earn the channel points.",
    license="GPLv3+",
    keywords="python bot streaming script miner twitch channel-points",
    url="https://github.com/krabhi4/twitch-miner",
    packages=setuptools.find_packages(),
    include_package_data=True,
    install_requires=[
        "requests",
        "websocket-client",
        "pillow",
        "python-dateutil",
        "emoji",
        "millify",
        "pre-commit",
        "colorama",
        "flask",
        "irc",
        "pandas",
        "pytz",
        "validators"
    ],
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    classifiers=[
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Topic :: Utilities",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering",
        "Topic :: Software Development :: Version Control :: Git",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Natural Language :: English",
    ],
    python_requires=">=3.10",
)
