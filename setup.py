from setuptools import setup
from setuptools import find_packages

setup(name='elephas',
      version='0.3-bp0.3.1',
      description='Deep learning on Spark with Keras',
      url='https://github.com/b13n3rd/elephas',
      download_url='https://github.com/maxpumperla/elephas/tarball/0.3',
      author='Max Pumperla',
      author_email='max.pumperla@googlemail.com',
      install_requires=['keras', 'hyperas', 'flask', 'pyspark' ,'tensorflow'],
      license='MIT',
      packages=find_packages(),
      zip_safe=False)
