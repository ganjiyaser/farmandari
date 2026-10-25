from setuptools import setup, find_packages

setup(
    name="farmandari",
    version="1.0.0",
    description="سیستم مدیریت امور دفتری فرمانداری",
    author="Ganjiyaser@gmail.com",
    packages=find_packages(),
    install_requires=[
        "PyQt6>=6.4.0",
        "PyQt6-Fluent-Widgets>=1.11.0",
        "SQLAlchemy>=2.0.0",
        "pydantic>=2.5.0",
        "pydantic-settings>=2.0.0",
        "requests>=2.28.0",
        "Pillow>=10.0.0",
        "openpyxl>=3.1.0",
        "reportlab>=4.0.0",
        "python-dateutil>=2.8.0",
        "pyserial>=3.5",
        "jdatetime>=4.0.0",
    ],
    entry_points={
        "console_scripts": [
            "farmandari=main:main",
        ],
    },
    python_requires=">=3.9",
)
