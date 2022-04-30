# pylint: disable=all
import importlib.metadata

dist = importlib.metadata.distribution('aiomarionette')

project = dist.metadata['Name']
version = release = dist.version
copyright = '2022 Dustin C. Hatch'

extensions = [
    'sphinx.ext.autodoc'
]

autodoc_member_order = 'groupwise'
