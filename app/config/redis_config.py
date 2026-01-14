"""
Redis Configuration
Centralized Redis connection and configuration management
"""
import os
from typing import Optional
import redis
from redis.connection import ConnectionPool


class RedisConfig:
    """Redis configuration and connection management"""
    
    def __init__(self):
        self.host = os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", "6379"))
        self.db = int(os.getenv("REDIS_DB", "0"))
        self.password = os.getenv("REDIS_PASSWORD")
        self.decode_responses = True
        
        # Connection pool for better performance
        self.pool = ConnectionPool(
            host=self.host,
            port=self.port,
            db=self.db,
            password=self.password,
            decode_responses=self.decode_responses,
            max_connections=50,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
    
    def get_client(self) -> redis.Redis:
        """Get Redis client from connection pool"""
        return redis.Redis(connection_pool=self.pool)
    
    def health_check(self) -> bool:
        """Check if Redis is accessible"""
        try:
            client = self.get_client()
            client.ping()
            return True
        except Exception as e:
            print(f"Redis health check failed: {e}")
            return False


# Global Redis configuration instance
redis_config = RedisConfig()


def get_redis_client() -> redis.Redis:
    """Dependency function to get Redis client"""
    return redis_config.get_client()
