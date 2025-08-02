#!/usr/bin/env python3
"""
CoRamTix Professional Status Monitor
A production-ready Flask application for monitoring website uptime and status.
"""

import os
import sys
import time
import threading
import logging
import sqlite3
import asyncio
import aiohttp
import yaml
import signal
import json
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

# Flask imports
from flask import Flask, jsonify, request, render_template_string
from werkzeug.serving import make_server
from werkzeug.middleware.proxy_fix import ProxyFix

# Rate limiting (optional dependency)
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    RATE_LIMITING_AVAILABLE = True
except ImportError:
    RATE_LIMITING_AVAILABLE = False

# Application metadata
__version__ = "2.0.0"
__author__ = "CoRamTix Systems"

# Configuration Management
@dataclass
class AppConfig:
    """Application configuration with validation"""
    database_path: str = "data/status.db"
    config_file: str = "config.yaml"
    port: int = 8080
    host: str = "0.0.0.0"
    debug: bool = False
    secret_key: str = "change-this-in-production"
    redis_url: str = "redis://localhost:6379"
    check_interval: int = 60
    request_timeout: int = 10
    max_workers: int = 5
    log_level: str = "INFO"
    log_file: str = "logs/status_monitor.log"
    
    @classmethod
    def from_environment(cls) -> 'AppConfig':
        """Create configuration from environment variables"""
        return cls(
            database_path=os.getenv('DATABASE_PATH', cls.database_path),
            config_file=os.getenv('CONFIG_FILE', cls.config_file),
            port=int(os.getenv('PORT', cls.port)),
            host=os.getenv('HOST', cls.host),
            debug=os.getenv('FLASK_ENV') == 'development',
            secret_key=os.getenv('SECRET_KEY', cls.secret_key),
            redis_url=os.getenv('REDIS_URL', cls.redis_url),
            check_interval=int(os.getenv('CHECK_INTERVAL', cls.check_interval)),
            request_timeout=int(os.getenv('REQUEST_TIMEOUT', cls.request_timeout)),
            max_workers=int(os.getenv('MAX_WORKERS', cls.max_workers)),
            log_level=os.getenv('LOG_LEVEL', cls.log_level),
            log_file=os.getenv('LOG_FILE', cls.log_file)
        )

# Logging Configuration
class Logger:
    """Enhanced logging configuration"""
    
    @staticmethod
    def setup_logging(config: AppConfig) -> logging.Logger:
        """Setup comprehensive logging"""
        # Create logs directory
        log_dir = Path(config.log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Configure logger
        logger = logging.getLogger('status_monitor')
        logger.setLevel(getattr(logging, config.log_level))
        
        # Remove existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # File handler
        file_handler = logging.FileHandler(config.log_file)
        file_handler.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG if config.debug else logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)d]'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger

# Database Management
class DatabaseManager:
    """Production-ready database management with connection pooling"""
    
    def __init__(self, db_path: str, logger: logging.Logger):
        self.db_path = Path(db_path)
        self.logger = logger
        self._ensure_directory()
        self._initialize_schema()
    
    def _ensure_directory(self):
        """Ensure database directory exists"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections with enhanced error handling"""
        conn = None
        try:
            conn = sqlite3.connect(
                str(self.db_path), 
                timeout=30,
                isolation_level=None  # Autocommit mode
            )
            conn.row_factory = sqlite3.Row
            
            # Enable WAL mode for better concurrency
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA cache_size=1000')
            conn.execute('PRAGMA temp_store=memory')
            
            yield conn
            
        except sqlite3.Error as e:
            self.logger.error(f"Database error: {e}")
            if conn:
                conn.rollback()
            raise
        except Exception as e:
            self.logger.error(f"Unexpected database error: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
    
    def _initialize_schema(self):
        """Initialize database schema with proper indexes"""
        with self.get_connection() as conn:
            # Sites table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    url TEXT NOT NULL,
                    status TEXT DEFAULT 'Unknown',
                    last_change REAL DEFAULT 0,
                    last_checked TEXT DEFAULT 'Never',
                    total_uptime REAL DEFAULT 0,
                    total_downtime REAL DEFAULT 0,
                    response_time REAL DEFAULT NULL,
                    status_code INTEGER DEFAULT NULL,
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    updated_at REAL DEFAULT (strftime('%s', 'now'))
                )
            ''')
            
            # Status history table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    response_time REAL,
                    status_code INTEGER,
                    error_message TEXT,
                    checked_at REAL DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (site_id) REFERENCES sites (id)
                )
            ''')
            
            # Incidents table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id INTEGER NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL DEFAULT NULL,
                    duration REAL DEFAULT NULL,
                    severity TEXT DEFAULT 'minor',
                    description TEXT,
                    resolved BOOLEAN DEFAULT FALSE,
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (site_id) REFERENCES sites (id)
                )
            ''')
            
            # Create indexes for better performance
            conn.execute('CREATE INDEX IF NOT EXISTS idx_sites_name ON sites(name)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_sites_status ON sites(status)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_history_site_id ON status_history(site_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_history_checked_at ON status_history(checked_at)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_incidents_site_id ON incidents(site_id)')
            
    def execute_query(self, query: str, params: Tuple = None) -> List[sqlite3.Row]:
        """Execute SELECT query with error handling"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params or ())
                return cursor.fetchall()
        except Exception as e:
            self.logger.error(f"Query execution failed: {query} - {e}")
            return []
    
    def execute_update(self, query: str, params: Tuple = None) -> int:
        """Execute INSERT/UPDATE/DELETE query"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params or ())
                return cursor.rowcount
        except Exception as e:
            self.logger.error(f"Update execution failed: {query} - {e}")
            return 0

# Configuration Management
class ConfigManager:
    """Enhanced configuration management"""
    
    def __init__(self, config_file: str, logger: logging.Logger):
        self.config_file = Path(config_file)
        self.logger = logger
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """Load configuration with validation and defaults"""
        if not self.config_file.exists():
            self._create_default_config()
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # Validate configuration
            self._validate_config(config)
            return config
            
        except Exception as e:
            self.logger.error(f"Configuration load failed: {e}")
            return self._get_default_config()
    
    def _create_default_config(self):
        """Create default configuration file"""
        default_config = self._get_default_config()
        
        # Ensure directory exists
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, indent=2)
        
        self.logger.info(f"Created default configuration: {self.config_file}")
    
    def _get_default_config(self) -> Dict:
        """Get default configuration"""
        return {
            'application': {
                'name': 'CoRamTix Status Monitor',
                'version': __version__,
                'check_interval': 60,
                'request_timeout': 10,
                'max_concurrent_checks': 10
            },
            'sites': [
                {
                    'name': 'Google',
                    'url': 'https://www.google.com',
                    'expected_status': 200,
                    'timeout': 10
                },
                {
                    'name': 'GitHub',
                    'url': 'https://www.github.com',
                    'expected_status': 200,
                    'timeout': 10
                },
                {
                    'name': 'Stack Overflow',
                    'url': 'https://stackoverflow.com',
                    'expected_status': 200,
                    'timeout': 10
                }
            ],
            'notifications': {
                'enabled': False,
                'webhook_url': '',
                'email_enabled': False,
                'email_smtp_server': '',
                'email_from': '',
                'email_to': []
            },
            'ui': {
                'theme': 'professional',
                'refresh_interval': 30,
                'show_response_times': True,
                'show_historical_data': True
            }
        }
    
    def _validate_config(self, config: Dict):
        """Validate configuration structure"""
        required_sections = ['sites']
        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required configuration section: {section}")
        
        if not isinstance(config['sites'], list):
            raise ValueError("'sites' must be a list")
        
        for i, site in enumerate(config['sites']):
            if not isinstance(site, dict):
                raise ValueError(f"Site {i} must be a dictionary")
            if 'name' not in site or 'url' not in site:
                raise ValueError(f"Site {i} missing required 'name' or 'url'")
    
    def get_sites(self) -> List[Dict]:
        """Get configured sites"""
        return self.config.get('sites', [])
    
    def get_check_interval(self) -> int:
        """Get check interval"""
        return self.config.get('application', {}).get('check_interval', 60)
    
    def get_request_timeout(self) -> int:
        """Get request timeout"""
        return self.config.get('application', {}).get('request_timeout', 10)

# Status Monitoring Engine
class StatusMonitor:
    """Advanced asynchronous status monitoring system"""
    
    def __init__(self, app_config: AppConfig, db_manager: DatabaseManager, 
                 config_manager: ConfigManager, logger: logging.Logger):
        self.app_config = app_config
        self.db_manager = db_manager
        self.config_manager = config_manager
        self.logger = logger
        self.running = False
        self.monitor_thread = None
        self._initialize_sites()
    
    def _initialize_sites(self):
        """Initialize sites in database"""
        sites = self.config_manager.get_sites()
        current_time = time.time()
        
        for site in sites:
            # Insert or update site
            self.db_manager.execute_update('''
                INSERT OR REPLACE INTO sites 
                (name, url, last_change, updated_at) 
                VALUES (?, ?, ?, ?)
            ''', (site['name'], site['url'], current_time, current_time))
        
        self.logger.info(f"Initialized {len(sites)} sites for monitoring")
    
    async def check_site(self, session: aiohttp.ClientSession, site: Dict) -> Dict:
        """Check individual site status with comprehensive error handling"""
        name = site['name']
        url = site['url']
        timeout = site.get('timeout', self.config_manager.get_request_timeout())
        expected_status = site.get('expected_status', 200)
        
        start_time = time.time()
        result = {
            'name': name,
            'url': url,
            'status': 'Down',
            'response_time': None,
            'status_code': None,
            'error': None,
            'checked_at': start_time
        }
        
        try:
            client_timeout = aiohttp.ClientTimeout(total=timeout)
            headers = {
                'User-Agent': f'StatusMonitor/{__version__} (Professional Monitoring Service)',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            async with session.get(
                url, 
                timeout=client_timeout, 
                headers=headers,
                ssl=False,
                allow_redirects=True
            ) as response:
                end_time = time.time()
                response_time = end_time - start_time
                
                # Determine status based on response code
                if expected_status == response.status or (200 <= response.status < 300):
                    status = 'Online'
                else:
                    status = 'Down'
                
                result.update({
                    'status': status,
                    'response_time': response_time,
                    'status_code': response.status
                })
                
                self.logger.debug(f"{name}: {status} ({response.status}) - {response_time:.3f}s")
                
        except asyncio.TimeoutError:
            result.update({
                'response_time': time.time() - start_time,
                'error': 'Request timeout'
            })
            self.logger.warning(f"{name}: Timeout after {timeout}s")
            
        except aiohttp.ClientError as e:
            result.update({
                'response_time': time.time() - start_time,
                'error': f'Client error: {str(e)}'
            })
            self.logger.warning(f"{name}: Client error - {e}")
            
        except Exception as e:
            result.update({
                'response_time': time.time() - start_time,
                'error': f'Unexpected error: {str(e)}'
            })
            self.logger.error(f"{name}: Unexpected error - {e}")
        
        return result
    
    async def check_all_sites(self):
        """Check all configured sites concurrently"""
        sites = self.config_manager.get_sites()
        if not sites:
            self.logger.warning("No sites configured for monitoring")
            return
        
        # Configure aiohttp session
        connector = aiohttp.TCPConnector(
            limit=self.app_config.max_workers,
            limit_per_host=3,
            ttl_dns_cache=300,
            use_dns_cache=True
        )
        
        timeout = aiohttp.ClientTimeout(total=self.config_manager.get_request_timeout())
        
        try:
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            ) as session:
                # Create tasks for all sites
                tasks = [self.check_site(session, site) for site in sites]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                success_count = 0
                for result in results:
                    if isinstance(result, Exception):
                        self.logger.error(f"Site check failed: {result}")
                        continue
                    
                    try:
                        self._update_site_status(result)
                        if result['status'] == 'Online':
                            success_count += 1
                    except Exception as e:
                        self.logger.error(f"Failed to update {result.get('name', 'unknown')}: {e}")
                
                self.logger.info(f"Monitoring cycle completed: {success_count}/{len(sites)} sites online")
                
        except Exception as e:
            self.logger.error(f"Monitoring session failed: {e}")
    
    def _update_site_status(self, result: Dict):
        """Update site status in database with history tracking"""
        current_time = time.time()
        timestamp = datetime.fromtimestamp(current_time).strftime("%Y-%m-%d %H:%M:%S")
        
        # Get current site data
        site_data = self.db_manager.execute_query(
            "SELECT * FROM sites WHERE name = ?", (result['name'],)
        )
        
        if not site_data:
            self.logger.warning(f"Site not found in database: {result['name']}")
            return
        
        site = site_data[0]
        previous_status = site['status']
        time_since_change = current_time - site['last_change']
        
        # Update uptime/downtime counters
        new_uptime = site['total_uptime']
        new_downtime = site['total_downtime']
        
        if previous_status == 'Online':
            new_uptime += time_since_change
        elif previous_status == 'Down':
            new_downtime += time_since_change
        
        # Update site status
        self.db_manager.execute_update('''
            UPDATE sites SET 
                status = ?, last_change = ?, last_checked = ?,
                total_uptime = ?, total_downtime = ?, response_time = ?,
                status_code = ?, updated_at = ?
            WHERE name = ?
        ''', (
            result['status'], current_time, timestamp,
            new_uptime, new_downtime, result['response_time'],
            result['status_code'], current_time, result['name']
        ))
        
        # Record status history
        self.db_manager.execute_update('''
            INSERT INTO status_history 
            (site_id, status, response_time, status_code, error_message, checked_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            site['id'], result['status'], result['response_time'],
            result['status_code'], result.get('error'), current_time
        ))
        
        # Handle status changes
        if previous_status != result['status']:
            self._handle_status_change(site, previous_status, result)
    
    def _handle_status_change(self, site: sqlite3.Row, old_status: str, result: Dict):
        """Handle status changes and incident management"""
        self.logger.info(
            f"Status change detected: {site['name']} {old_status} -> {result['status']}"
        )
        
        # Handle incident creation/resolution
        if result['status'] == 'Down' and old_status == 'Online':
            # Create new incident
            self.db_manager.execute_update('''
                INSERT INTO incidents (site_id, start_time, description)
                VALUES (?, ?, ?)
            ''', (
                site['id'], 
                time.time(),
                f"Site went down: {result.get('error', 'Unknown error')}"
            ))
            
        elif result['status'] == 'Online' and old_status == 'Down':
            # Resolve existing incident
            current_time = time.time()
            self.db_manager.execute_update('''
                UPDATE incidents SET 
                    end_time = ?, duration = ?, resolved = TRUE
                WHERE site_id = ? AND resolved = FALSE
            ''', (
                current_time,
                current_time - site['last_change'],
                site['id']
            ))
    
    def monitor_loop(self):
        """Main monitoring loop with error recovery"""
        self.running = True
        check_interval = self.config_manager.get_check_interval()
        
        self.logger.info(f"Starting monitoring loop (interval: {check_interval}s)")
        
        while self.running:
            try:
                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Run monitoring cycle
                start_time = time.time()
                loop.run_until_complete(self.check_all_sites())
                cycle_duration = time.time() - start_time
                
                self.logger.debug(f"Monitoring cycle took {cycle_duration:.2f}s")
                
                # Clean up
                loop.close()
                
                # Wait for next cycle
                if self.running:
                    time.sleep(check_interval)
                    
            except KeyboardInterrupt:
                self.logger.info("Monitoring interrupted by user")
                break
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                time.sleep(30)  # Brief pause before retry
    
    def start(self):
        """Start monitoring in background thread"""
        if not self.monitor_thread or not self.monitor_thread.is_alive():
            self.monitor_thread = threading.Thread(
                target=self.monitor_loop,
                daemon=True,
                name="StatusMonitorThread"
            )
            self.monitor_thread.start()
            self.logger.info("Status monitoring started")
    
    def stop(self):
        """Stop monitoring gracefully"""
        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.logger.info("Stopping status monitor...")
            self.monitor_thread.join(timeout=10)
        self.logger.info("Status monitor stopped")

# Utility Functions
def format_duration(seconds: float) -> str:
    """Format duration in human-readable format"""
    if not seconds or seconds < 0:
        return "0s"
    
    seconds = int(seconds)
    
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s" if secs else f"{minutes}m"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d {hours}h" if hours else f"{days}d"

def format_bytes(bytes_count: int) -> str:
    """Format bytes in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.1f}{unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.1f}TB"

# Flask Application Factory
def create_flask_app(app_config: AppConfig, db_manager: DatabaseManager, 
                    config_manager: ConfigManager, logger: logging.Logger) -> Flask:
    """Create and configure Flask application"""
    
    app = Flask(__name__)
    app.config['SECRET_KEY'] = app_config.secret_key
    app.config['JSON_SORT_KEYS'] = False
    
    # Add proxy fix for deployment behind reverse proxy
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    # Setup rate limiting if available
    limiter = None
    if RATE_LIMITING_AVAILABLE and not app_config.debug:
        try:
            limiter = Limiter(
                app,
                key_func=get_remote_address,
                default_limits=["1000 per hour", "100 per minute"],
                storage_uri=app_config.redis_url
            )
            logger.info("Rate limiting enabled")
        except Exception as e:
            logger.warning(f"Rate limiting disabled: {e}")
    
    # Enhanced HTML template
    HTML_TEMPLATE = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{{app_name}} - Status Dashboard</title>
        <link rel="icon" type="image/x-icon" href="data:image/x-icon;base64,AAABAAEAEBAAAAEAIABoBAAAFgAAACgAAAAQAAAAIAAAAAEAIAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A////AP///wD///8A27e3/9u3t//bt7f/27e3/+7d3f/u3d3/7t3d/+7d3f/bt7f/27e3/9u3t//bt7f/////AP///wD///8A////AP///wD///8A27e3/+7d3f/u3d3/7t3d/+7d3f/u3d3/7t3d/+7d3f/u3d3/7t3d/+7d3f/bt7f/////AP///wD///8A////AP///wD///8A27e3/+7d3f/u3d3/7t3d/+7d3f/u3d3/7t3d/+7d3f/u3d3/7t3d/+7d3f/bt7f/////AP///wD///8A////AP///wD///8A27e3/+7d3f/u3d3/7t3d/+7d3f/u3d3/7t3d/+7d3f/u3d3/7t3d/+7d3f/bt7f/////AP///wD///8A////AP///wD///8A27e3/+7d3f/u3d3/7t3d/+7d3f/u3d3/7t3d/+7d3f/u3d3/7t3d/+7d3f/bt7f/////AP///wD///8A">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                color: #333;
            }
            
            .container {
                max-width: 1400px;
                margin: 0 auto;
                padding: 20px;
            }
            
            .header {
                background: rgba(255, 255, 255, 0.95);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 30px;
                margin-bottom: 30px;
                text-align: center;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            }
            
            .brand {
                font-size: 2.5rem;
                font-weight: 800;
                background: linear-gradient(45deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 10px;
            }
            
            .subtitle {
                color: #666;
                font-size: 1.1rem;
                margin-bottom: 20px;
            }
            
            .status-overview {
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 30px;
                margin-top: 20px;
            }
            
            .overall-status {
                font-size: 1.8rem;
                font-weight: 600;
                padding: 15px 30px;
                border-radius: 50px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            
            .status-operational {
                background: linear-gradient(45deg, #4CAF50, #45a049);
                color: white;
            }
            
            .status-degraded {
                background: linear-gradient(45deg, #ff9800, #f57c00);
                color: white;
            }
            
            .status-bar {
                display: flex;
                gap: 4px;
                align-items: center;
            }
            
            .status-block {
                width: 20px;
                height: 40px;
                border-radius: 6px;
                background: #ddd;
                transition: all 0.3s ease;
            }
            
            .status-block.online { background: #4CAF50; }
            .status-block.degraded { background: #ff9800; }
            .status-block.offline { background: #f44336; }
            
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }
            
            .stat-card {
                background: rgba(255, 255, 255, 0.9);
                backdrop-filter: blur(10px);
                border-radius: 15px;
                padding: 25px;
                text-align: center;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
                transition: transform 0.3s ease;
            }
            
            .stat-card:hover {
                transform: translateY(-5px);
            }
            
            .stat-value {
                font-size: 2.5rem;
                font-weight: 700;
                margin-bottom: 10px;
                background: linear-gradient(45deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            
            .stat-label {
                color: #666;
                font-size: 0.9rem;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            
            .sites-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
                gap: 25px;
                margin-top: 30px;
            }
            
            .site-card {
                background: rgba(255, 255, 255, 0.95);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 30px;
                box-shadow: 0 15px 35px rgba(0, 0, 0, 0.1);
                border-left: 5px solid #ddd;
                transition: all 0.3s ease;
            }
            
            .site-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 20px 45px rgba(0, 0, 0, 0.15);
            }
            
            .site-online { border-left-color: #4CAF50; }
            .site-down { border-left-color: #f44336; }
            .site-unknown { border-left-color: #9e9e9e; }
            
            .site-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
            }
            
            .site-name {
                font-size: 1.4rem;
                font-weight: 600;
                color: #333;
            }
            
            .site-status {
                padding: 8px 16px;
                border-radius: 20px;
                font-size: 0.9rem;
                font-weight: 500;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .status-online { background: #e8f5e8; color: #4CAF50; }
            .status-down { background: #ffebee; color: #f44336; }
            .status-unknown { background: #f5f5f5; color: #9e9e9e; }
            
            .site-metrics {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 15px;
                margin-top: 20px;
            }
            
            .metric {
                background: #f8f9fa;
                border-radius: 10px;
                padding: 15px;
                text-align: center;
            }
            
            .metric-value {
                font-size: 1.2rem;
                font-weight: 600;
                color: #333;
                margin-bottom: 5px;
            }
            
            .metric-label {
                font-size: 0.8rem;
                color: #666;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .site-url {
                font-family: 'Monaco', 'Consolas', monospace;
                background: #f0f0f0;
                padding: 10px;
                border-radius: 8px;
                font-size: 0.85rem;
                color: #666;
                margin-top: 15px;
                word-break: break-all;
            }
            
            .footer {
                text-align: center;
                margin-top: 50px;
                padding: 30px;
                background: rgba(255, 255, 255, 0.9);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                color: #666;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            }
            
            .loading {
                text-align: center;
                padding: 50px;
                font-size: 1.2rem;
                color: #666;
            }
            
            .error {
                background: #ffebee;
                color: #c62828;
                padding: 20px;
                border-radius: 10px;
                border-left: 4px solid #f44336;
                margin: 20px 0;
            }
            
            @media (max-width: 768px) {
                .container { padding: 15px; }
                .header { padding: 20px; }
                .brand { font-size: 2rem; }
                .sites-grid { grid-template-columns: 1fr; }
                .status-overview { flex-direction: column; gap: 20px; }
            }
            
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
            
            .loading { animation: pulse 2s infinite; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="brand">{{app_name}}</div>
                <div class="subtitle">Professional System Status Monitor v{{version}}</div>
                <div class="status-overview">
                    <div class="overall-status" id="overall-status">
                        <div class="loading">Initializing system status...</div>
                    </div>
                    <div class="status-bar" id="status-bar"></div>
                </div>
            </div>
            
            <div class="stats-grid" id="stats-grid">
                <div class="loading">Loading system statistics...</div>
            </div>
            
            <div class="sites-grid" id="sites-grid">
                <div class="loading">Loading monitored services...</div>
            </div>
            
            <div class="footer">
                <p><strong>{{app_name}}</strong> &copy; 2025 {{author}}</p>
                <p>Last Updated: <span id="last-update">Never</span></p>
                <p>Monitoring <span id="site-count">0</span> services every <span id="check-interval">60</span> seconds</p>
            </div>
        </div>
        
        <script>
            class StatusDashboard {
                constructor() {
                    this.lastUpdate = 0;
                    this.refreshInterval = 30000; // 30 seconds
                    this.init();
                }
                
                init() {
                    this.updateStatus();
                    setInterval(() => this.updateStatus(), this.refreshInterval);
                    
                    // Handle visibility changes
                    document.addEventListener('visibilitychange', () => {
                        if (!document.hidden) {
                            this.updateStatus();
                        }
                    });
                }
                
                async updateStatus() {
                    try {
                        const response = await fetch('/api/status');
                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                        }
                        
                        const data = await response.json();
                        this.renderStatus(data);
                        this.renderStats(data);
                        this.renderSites(data);
                        this.updateFooter(data);
                        
                    } catch (error) {
                        console.error('Status update failed:', error);
                        this.renderError(error.message);
                    }
                }
                
                renderStatus(data) {
                    const statusEl = document.getElementById('overall-status');
                    const isOperational = data.overall_status === 'operational';
                    
                    statusEl.className = `overall-status ${isOperational ? 'status-operational' : 'status-degraded'}`;
                    statusEl.textContent = isOperational ? 'All Systems Operational' : 'System Issues Detected';
                    
                    // Update status bar
                    this.renderStatusBar(data.sites);
                }
                
                renderStatusBar(sites) {
                    const barEl = document.getElementById('status-bar');
                    const siteList = Object.values(sites);
                    const total = siteList.length;
                    const online = siteList.filter(site => site.status === 'Online').length;
                    
                    barEl.innerHTML = '';
                    
                    for (let i = 0; i < 20; i++) {
                        const block = document.createElement('div');
                        block.className = 'status-block';
                        
                        if (total > 0) {
                            const ratio = online / total;
                            if (i < Math.floor(ratio * 20)) {
                                block.classList.add(ratio === 1 ? 'online' : 'degraded');
                            } else {
                                block.classList.add('offline');
                            }
                        }
                        
                        barEl.appendChild(block);
                    }
                }
                
                renderStats(data) {
                    const sites = Object.values(data.sites);
                    const total = sites.length;
                    const online = sites.filter(site => site.status === 'Online').length;
                    const avgUptime = sites.reduce((sum, site) => {
                        return sum + parseFloat(site.uptime_percent);
                    }, 0) / total;
                    
                    const avgResponseTime = sites
                        .filter(site => site.response_time)
                        .reduce((sum, site) => sum + site.response_time, 0) / 
                        sites.filter(site => site.response_time).length;
                    
                    const statsHtml = `
                        <div class="stat-card">
                            <div class="stat-value">${online}/${total}</div>
                            <div class="stat-label">Services Online</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">${avgUptime.toFixed(1)}%</div>
                            <div class="stat-label">Average Uptime</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">${avgResponseTime ? Math.round(avgResponseTime * 1000) : 'N/A'}</div>
                            <div class="stat-label">Avg Response (ms)</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">${data.check_interval}s</div>
                            <div class="stat-label">Check Interval</div>
                        </div>
                    `;
                    
                    document.getElementById('stats-grid').innerHTML = statsHtml;
                }
                
                renderSites(data) {
                    const container = document.getElementById('sites-grid');
                    
                    if (Object.keys(data.sites).length === 0) {
                        container.innerHTML = '<div class="error">No services configured for monitoring</div>';
                        return;
                    }
                    
                    const sitesHtml = Object.entries(data.sites).map(([name, site]) => {
                        const responseTime = site.response_time ? 
                            `${Math.round(site.response_time * 1000)}ms` : 'N/A';
                        
                        return `
                            <div class="site-card site-${site.status.toLowerCase()}">
                                <div class="site-header">
                                    <div class="site-name">${name}</div>
                                    <div class="site-status status-${site.status.toLowerCase()}">${site.status}</div>
                                </div>
                                <div class="site-metrics">
                                    <div class="metric">
                                        <div class="metric-value">${site.uptime_percent}</div>
                                        <div class="metric-label">Uptime</div>
                                    </div>
                                    <div class="metric">
                                        <div class="metric-value">${responseTime}</div>
                                        <div class="metric-label">Response Time</div>
                                    </div>
                                    <div class="metric">
                                        <div class="metric-value">${site.uptime}</div>
                                        <div class="metric-label">Total Uptime</div>
                                    </div>
                                    <div class="metric">
                                        <div class="metric-value">${site.last_checked}</div>
                                        <div class="metric-label">Last Checked</div>
                                    </div>
                                </div>
                                <div class="site-url">${site.url}</div>
                            </div>
                        `;
                    }).join('');
                    
                    container.innerHTML = sitesHtml;
                }
                
                updateFooter(data) {
                    const siteCount = Object.keys(data.sites).length;
                    document.getElementById('last-update').textContent = new Date().toLocaleString();
                    document.getElementById('site-count').textContent = siteCount;
                    document.getElementById('check-interval').textContent = data.check_interval || 60;
                }
                
                renderError(message) {
                    document.getElementById('overall-status').innerHTML = 
                        `<span class="status-degraded">System Error: ${message}</span>`;
                    document.getElementById('sites-grid').innerHTML = 
                        `<div class="error">Failed to load service status: ${message}</div>`;
                }
            }
            
            // Initialize dashboard when page loads
            document.addEventListener('DOMContentLoaded', () => {
                new StatusDashboard();
            });
        </script>
    </body>
    </html>
    '''
    
    # Routes
    @app.route('/')
    def home():
        """Main dashboard page"""
        config = config_manager.config
        app_name = config.get('application', {}).get('name', 'Status Monitor')
        
        return render_template_string(
            HTML_TEMPLATE,
            app_name=app_name,
            version=__version__,
            author=__author__
        )
    
    @app.route('/api/status')
    def api_status():
        """Main status API endpoint"""
        try:
            sites_data = db_manager.execute_query("SELECT * FROM sites ORDER BY name")
            
            response_data = {
                "sites": {},
                "timestamp": time.time(),
                "overall_status": "operational",
                "version": __version__,
                "check_interval": config_manager.get_check_interval()
            }
            
            all_operational = True
            current_time = time.time()
            
            for site in sites_data:
                # Calculate real-time uptime
                time_since_change = current_time - site['last_change']
                
                display_uptime = site['total_uptime']
                display_downtime = site['total_downtime']
                
                if site['status'] == 'Online':
                    display_uptime += time_since_change
                elif site['status'] == 'Down':
                    display_downtime += time_since_change
                
                total_time = display_uptime + display_downtime
                uptime_percent = (display_uptime / total_time * 100) if total_time > 0 else 100.0
                
                response_data["sites"][site['name']] = {
                    "status": site['status'],
                    "uptime": format_duration(display_uptime),
                    "downtime": format_duration(display_downtime),
                    "uptime_percent": f"{uptime_percent:.3f}%",
                    "last_checked": site['last_checked'] or 'Never',
                    "response_time": site['response_time'],
                    "url": site['url'],
                    "status_code": site['status_code']
                }
                
                if site['status'] != "Online":
                    all_operational = False
            
            if not all_operational:
                response_data["overall_status"] = "degraded"
            
            return jsonify(response_data)
            
        except Exception as e:
            logger.error(f"Status API error: {e}")
            return jsonify({
                "error": "Internal server error",
                "message": str(e),
                "timestamp": time.time()
            }), 500
    
    @app.route('/api/health')
    def api_health():
        """Health check endpoint"""
        try:
            # Test database connectivity
            db_manager.execute_query("SELECT 1")
            
            return jsonify({
                "status": "healthy",
                "timestamp": time.time(),
                "version": __version__,
                "database": "connected",
                "monitored_sites": len(config_manager.get_sites())
            })
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return jsonify({
                "status": "unhealthy",
                "timestamp": time.time(),
                "error": str(e)
            }), 503
    
    @app.route('/api/history/<site_name>')
    def api_site_history(site_name: str):
        """Get historical data for a specific site"""
        try:
            # Get site ID
            site_data = db_manager.execute_query(
                "SELECT id FROM sites WHERE name = ?", (site_name,)
            )
            
            if not site_data:
                return jsonify({"error": "Site not found"}), 404
            
            site_id = site_data[0]['id']
            
            # Get recent history (last 24 hours)
            since_time = time.time() - 86400  # 24 hours ago
            history = db_manager.execute_query('''
                SELECT status, response_time, status_code, checked_at
                FROM status_history 
                WHERE site_id = ? AND checked_at > ?
                ORDER BY checked_at DESC
                LIMIT 100
            ''', (site_id, since_time))
            
            history_data = []
            for record in history:
                history_data.append({
                    "status": record['status'],
                    "response_time": record['response_time'],
                    "status_code": record['status_code'],
                    "timestamp": record['checked_at']
                })
            
            return jsonify({
                "site": site_name,
                "history": history_data,
                "count": len(history_data)
            })
            
        except Exception as e:
            logger.error(f"History API error: {e}")
            return jsonify({
                "error": "Internal server error",
                "message": str(e)
            }), 500
    
    @app.route('/api/incidents')
    def api_incidents():
        """Get current incidents"""
        try:
            incidents = db_manager.execute_query('''
                SELECT i.*, s.name as site_name 
                FROM incidents i
                JOIN sites s ON i.site_id = s.id
                WHERE i.resolved = FALSE
                ORDER BY i.start_time DESC
            ''')
            
            incidents_data = []
            for incident in incidents:
                incidents_data.append({
                    "id": incident['id'],
                    "site_name": incident['site_name'],
                    "start_time": incident['start_time'],
                    "duration": time.time() - incident['start_time'],
                    "description": incident['description'],
                    "severity": incident['severity']
                })
            
            return jsonify({
                "incidents": incidents_data,
                "count": len(incidents_data)
            })
            
        except Exception as e:
            logger.error(f"Incidents API error: {e}")
            return jsonify({
                "error": "Internal server error",
                "message": str(e)
            }), 500
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 errors"""
        return jsonify({
            "error": "Resource not found",
            "message": "The requested resource could not be found"
        }), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors"""
        logger.error(f"Internal server error: {error}")
        return jsonify({
            "error": "Internal server error",
            "message": "An unexpected error occurred"
        }), 500
    
    if limiter:
        @app.errorhandler(429)
        def ratelimit_handler(e):
            """Handle rate limiting"""
            return jsonify({
                "error": "Rate limit exceeded",
                "message": "Too many requests, please try again later",
                "retry_after": 60
            }), 429
    
    # Security headers
    @app.after_request
    def add_security_headers(response):
        """Add security headers to all responses"""
        if not app_config.debug:
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['X-XSS-Protection'] = '1; mode=block'
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        response.headers['X-Powered-By'] = f'StatusMonitor/{__version__}'
        return response
    
    return app

# Application Entry Point
class StatusMonitorApp:
    """Main application class with lifecycle management"""
    
    def __init__(self):
        self.app_config = AppConfig.from_environment()
        self.logger = Logger.setup_logging(self.app_config)
        
        self.db_manager = DatabaseManager(self.app_config.database_path, self.logger)
        self.config_manager = ConfigManager(self.app_config.config_file, self.logger)
        
        self.flask_app = create_flask_app(
            self.app_config, self.db_manager, 
            self.config_manager, self.logger
        )
        
        self.monitor = StatusMonitor(
            self.app_config, self.db_manager, 
            self.config_manager, self.logger
        )
        
        self.server = None
        self.running = False
    
    def start(self):
        """Start the application"""
        try:
            self.logger.info(f"Starting {__author__} Status Monitor v{__version__}")
            
            # Start monitoring
            self.monitor.start()
            
            # Create server
            self.server = make_server(
                self.app_config.host,
                self.app_config.port,
                self.flask_app,
                threaded=True
            )
            
            self.running = True
            
            self.logger.info(f"Server started on http://{self.app_config.host}:{self.app_config.port}")
            self.logger.info(f"Monitoring {len(self.config_manager.get_sites())} sites")
            
            # Serve forever
            self.server.serve_forever()
            
        except KeyboardInterrupt:
            self.logger.info("Application interrupted by user")
        except Exception as e:
            self.logger.error(f"Application startup failed: {e}")
            raise
        finally:
            self.stop()
    
    def stop(self):
        """Stop the application gracefully"""
        if not self.running:
            return
            
        self.logger.info("Shutting down application...")
        self.running = False
        
        # Stop monitoring
        if self.monitor:
            self.monitor.stop()
        
        # Stop server
        if self.server:
            self.server.shutdown()
        
        self.logger.info("Application stopped")
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}")
        self.stop()
        sys.exit(0)

def main():
    """Main entry point"""
    try:
        # Create application
        app = StatusMonitorApp()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, app.signal_handler)
        signal.signal(signal.SIGTERM, app.signal_handler)
        
        # Start application
        app.start()
        
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
