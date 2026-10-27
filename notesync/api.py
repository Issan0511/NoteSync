"""Stable extension API v1: ink rendering and the notebook host contract."""
from .InkModel import Stroke, paint_ink
from .Extensions import ExtensionHost

API_VERSION = 1
__all__ = ['API_VERSION', 'Stroke', 'paint_ink', 'ExtensionHost']
