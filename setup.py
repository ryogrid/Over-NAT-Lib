import os.path

import setuptools

root_dir = os.path.abspath(os.path.dirname(__file__))
readme_file = os.path.join(root_dir, 'README.md')
with open(readme_file, encoding='utf-8') as f:
    long_description = f.read()

install_requires = [
    'aiortc-dc >= 0.5.5',
    'gevent-websocket >= 0.10.1',
    'websockets >= 7.0',
    'websocket-client-py3 >= 0.15.0'
]

setuptools.setup(
    name='onatlib',
    version='0.0.2',
    description='A tool offers P2P communication to transfer files and connect pipes between PCs in different NATs',
    long_description_content_type="text/markdown",
    long_description=long_description,
    url='https://github.com/ryogrid/Over-NAT-Lib',
    author='Ryo Kanbayashi',
    author_email='ryo.contact@gmail.com',
    license='BSD',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
    ],
    packages=['onatlib','tools'],
    setup_requires=[],
    install_requires=install_requires,
)
