from setuptools import setup, find_packages

setup(
    name="farmandari",
    version="1.2.0",
    description="سیستم مدیریت امور دفتری فرمانداری",
    author="Ganjiyaser@gmail.com",
    packages=find_packages(),
    install_requires=[
        "PyQt5==5.15.11",
        "PyQt-Fluent-Widgets==1.11.3",
        'pywin32==228; sys_platform == "win32"',
        "SQLAlchemy==2.0.36",
        "requests==2.32.3",
        "openpyxl==3.1.5",
        "reportlab==3.6.13",
        "python-dateutil==2.9.0.post0",
        "pyserial==3.5",
        "jdatetime==4.1.0",
        "Pillow==9.5.0",
        "arabic-reshaper==3.0.0",
        "python-bidi==0.4.2",
        "packaging==24.2",
    ],
    entry_points={
        "console_scripts": [
            "farmandari=main:main",
        ],
    },
    # Windows 7 support: Python 3.9+ does not run on Windows 7 and PyQt6/Qt6
    # requires Windows 10+, so this branch targets Python 3.8 + PyQt5.
    python_requires=">=3.8,<3.9",
)
