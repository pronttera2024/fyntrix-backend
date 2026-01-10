"""
Base MCP (Model Context Protocol) Classes
Foundation for building MCP servers and tools
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Callable, Optional
from pydantic import BaseModel, Field
from enum import Enum


class MCPToolParameter(BaseModel):
    """Parameter definition for MCP tool"""
    name: str
    type: str  # "string", "number", "boolean", "object", "array"
    description: str
    required: bool = False
    enum: Optional[List[Any]] = None
    default: Optional[Any] = None


class MCPTool(BaseModel):
    """
    MCP Tool definition for function calling.
    Compatible with OpenAI function calling format.
    """
    name: str
    description: str
    parameters: List[MCPToolParameter]
    handler: Optional[Callable] = Field(default=None, exclude=True)
    
    def to_openai_function(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format"""
        properties = {}
        required = []
        
        for param in self.parameters:
            properties[param.name] = {
                "type": param.type,
                "description": param.description
            }
            if param.enum:
                properties[param.name]["enum"] = param.enum
            if param.default is not None:
                properties[param.name]["default"] = param.default
            
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }
    
    async def execute(self, **kwargs) -> Any:
        """Execute tool handler with arguments"""
        if self.handler is None:
            raise NotImplementedError(f"No handler registered for tool: {self.name}")
        
        # Call handler (sync or async)
        if asyncio.iscoroutinefunction(self.handler):
            return await self.handler(**kwargs)
        else:
            return self.handler(**kwargs)


class MCPResource(BaseModel):
    """MCP Resource (data source) definition"""
    name: str
    uri: str
    description: str
    mime_type: str = "application/json"
    handler: Optional[Callable] = Field(default=None, exclude=True)
    
    async def fetch(self) -> Any:
        """Fetch resource data"""
        if self.handler is None:
            raise NotImplementedError(f"No handler registered for resource: {self.name}")
        
        if asyncio.iscoroutinefunction(self.handler):
            return await self.handler()
        else:
            return self.handler()


class MCPServer(ABC):
    """
    Base class for MCP servers.
    An MCP server provides tools and resources for AI agents.
    """
    
    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.tools: Dict[str, MCPTool] = {}
        self.resources: Dict[str, MCPResource] = {}
    
    def register_tool(
        self,
        name: str,
        description: str,
        parameters: List[MCPToolParameter],
        handler: Callable
    ) -> MCPTool:
        """Register a tool with the server"""
        tool = MCPTool(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler
        )
        self.tools[name] = tool
        return tool
    
    def register_resource(
        self,
        name: str,
        uri: str,
        description: str,
        handler: Callable,
        mime_type: str = "application/json"
    ) -> MCPResource:
        """Register a resource with the server"""
        resource = MCPResource(
            name=name,
            uri=uri,
            description=description,
            mime_type=mime_type,
            handler=handler
        )
        self.resources[name] = resource
        return resource
    
    def get_tool(self, name: str) -> Optional[MCPTool]:
        """Get a tool by name"""
        return self.tools.get(name)
    
    def get_resource(self, name: str) -> Optional[MCPResource]:
        """Get a resource by name"""
        return self.resources.get(name)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools (OpenAI format)"""
        return [tool.to_openai_function() for tool in self.tools.values()]
    
    def list_resources(self) -> List[Dict[str, str]]:
        """List all available resources"""
        return [
            {
                "name": res.name,
                "uri": res.uri,
                "description": res.description,
                "mime_type": res.mime_type
            }
            for res in self.resources.values()
        ]
    
    async def call_tool(self, tool_name: str, **kwargs) -> Any:
        """Execute a tool by name"""
        tool = self.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")
        
        return await tool.execute(**kwargs)
    
    async def fetch_resource(self, resource_name: str) -> Any:
        """Fetch a resource by name"""
        resource = self.get_resource(resource_name)
        if not resource:
            raise ValueError(f"Resource not found: {resource_name}")
        
        return await resource.fetch()
    
    @abstractmethod
    async def initialize(self):
        """Initialize the server (register tools/resources)"""
        pass
    
    def get_server_info(self) -> Dict[str, Any]:
        """Get server information"""
        return {
            "name": self.name,
            "version": self.version,
            "tools_count": len(self.tools),
            "resources_count": len(self.resources)
        }


# Import asyncio at the end to avoid circular imports
import asyncio


def mcp_tool(
    name: str,
    description: str,
    parameters: List[MCPToolParameter]
):
    """Decorator to register a function as an MCP tool"""
    def decorator(func: Callable) -> Callable:
        func._mcp_tool_name = name
        func._mcp_tool_description = description
        func._mcp_tool_parameters = parameters
        return func
    return decorator


def mcp_resource(
    name: str,
    uri: str,
    description: str,
    mime_type: str = "application/json"
):
    """Decorator to register a function as an MCP resource"""
    def decorator(func: Callable) -> Callable:
        func._mcp_resource_name = name
        func._mcp_resource_uri = uri
        func._mcp_resource_description = description
        func._mcp_resource_mime_type = mime_type
        return func
    return decorator
