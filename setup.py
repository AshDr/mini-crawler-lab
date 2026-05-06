from setuptools import find_packages, setup


setup(
    name="mini-crawler-lab",
    version="0.1.0",
    description="A small HTTP fetcher built with httpx.",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=["httpx>=0.27"],
    extras_require={
        "render": ["playwright>=1.48"],
        "test": ["pytest>=8"],
    },
)
