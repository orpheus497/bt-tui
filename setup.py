from setuptools import setup, find_packages

setup(
    name="bsd-bt",
    version="0.1.0",
    description="FreeBSD Bluetooth TUI Manager",
    author="Orpheus497",
    author_email="example@example.com",
    url="https://github.com/example/bsd-bt",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "textual>=0.47.1",
    ],
    entry_points={
        "console_scripts": [
            "bsd-bt-tui=bt_tui:main",
            "bsd-bt-daemon=bt_daemon:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console :: Curses",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: BSD :: FreeBSD",
        "Programming Language :: Python :: 3",
        "Topic :: System :: Hardware :: Hardware Drivers",
    ],
    python_requires=">=3.8",
)
