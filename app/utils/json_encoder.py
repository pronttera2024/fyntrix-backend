"""
JSON Encoder Utilities
Handles serialization of numpy, pandas, and other non-standard types
"""
import json
from typing import Any
from datetime import datetime, date
import numpy as np
import pandas as pd


class NumpyPandasEncoder(json.JSONEncoder):
    """
    Custom JSON encoder that handles:
    - numpy types (int64, float64, etc.)
    - pandas DataFrames and Series
    - datetime objects
    """
    
    def default(self, obj: Any) -> Any:
        # Handle numpy integer types
        if isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
            return int(obj)
        
        # Handle numpy float types
        if isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
            return float(obj)
        
        # Handle numpy arrays
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        
        # Handle pandas DataFrames
        if isinstance(obj, pd.DataFrame):
            return obj.to_dict(orient='records')
        
        # Handle pandas Series
        if isinstance(obj, pd.Series):
            return obj.to_dict()
        
        # Handle datetime objects
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        
        # Handle pandas Timestamp
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        
        # Let the base class handle other types
        return super().default(obj)


def safe_json_dumps(obj: Any, **kwargs) -> str:
    """
    Safely serialize object to JSON, handling numpy/pandas types
    
    Args:
        obj: Object to serialize
        **kwargs: Additional arguments for json.dumps
        
    Returns:
        JSON string
    """
    return json.dumps(obj, cls=NumpyPandasEncoder, **kwargs)


def convert_numpy_types(obj: Any) -> Any:
    """
    Recursively convert numpy/pandas types to native Python types
    
    Args:
        obj: Object to convert
        
    Returns:
        Object with converted types
    """
    # Handle numpy types
    if isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
        return int(obj)
    
    if isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
        return float(obj)
    
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    
    # Handle pandas types
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient='records')
    
    if isinstance(obj, pd.Series):
        return obj.to_dict()
    
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    
    # Handle datetime
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    
    # Handle dictionaries recursively
    if isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    
    # Handle lists recursively
    if isinstance(obj, (list, tuple)):
        return [convert_numpy_types(item) for item in obj]
    
    # Return as-is for other types
    return obj
