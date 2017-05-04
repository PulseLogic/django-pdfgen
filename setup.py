from setuptools import setup, find_packages
import pdfgen


setup(
    name='django-pdfgen',
    version=pdfgen.__version__,
    url='https://github.com/vikingco/django-pdfgen',
    license='BSD',
    description='Generation of PDF documents',
    long_description=open('README.rst', 'r').read(),
    author='Jef Geskens, Unleashed NV',
    author_email='operations@unleashed.be',
    packages=find_packages('.'),
    zip_safe=False,
    install_requires='reportlab>=3.2.0',
    classifiers=[
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Operating System :: OS Independent',
        'Environment :: Web Environment',
        'Framework :: Django',
    ],
)
