"""
Migrate existing SQLite cache data to PostgreSQL
Migrates ai_recommendations and top_picks_runs from SQLite to PostgreSQL
"""
import sqlite3
import json
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.db import SessionLocal, Base, engine

# Import only the specific models we need
from app.models.analytics.ai_recommendation import AIRecommendation
from app.models.analytics.top_picks_run import TopPicksRun


def migrate_ai_recommendations():
    """Migrate AI recommendations from SQLite to PostgreSQL"""
    print("\n🔄 Migrating AI Recommendations...")
    
    sqlite_conn = sqlite3.connect('cache/ai_recommendations.db')
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()
    
    # Get all recommendations
    cursor.execute("SELECT * FROM ai_recommendations")
    rows = cursor.fetchall()
    
    if not rows:
        print("   ℹ️  No AI recommendations to migrate")
        sqlite_conn.close()
        return 0
    
    db: Session = SessionLocal()
    migrated = 0
    
    try:
        for row in rows:
            # Convert SQLite row to dict
            data = dict(row)
            
            # Parse datetime fields
            generated_at = None
            if data.get('generated_at_utc'):
                try:
                    generated_at = datetime.fromisoformat(data['generated_at_utc'].replace('Z', '+00:00'))
                except:
                    generated_at = datetime.utcnow()
            
            evaluated_at = None
            if data.get('evaluated_at_utc'):
                try:
                    evaluated_at = datetime.fromisoformat(data['evaluated_at_utc'].replace('Z', '+00:00'))
                except:
                    pass
            
            exit_time = None
            if data.get('exit_time_utc'):
                try:
                    exit_time = datetime.fromisoformat(data['exit_time_utc'].replace('Z', '+00:00'))
                except:
                    pass
            
            # Create PostgreSQL record
            rec = AIRecommendation(
                symbol=data.get('symbol'),
                mode=data.get('mode'),
                universe=data.get('universe', 'unknown'),
                source=data.get('source', 'legacy_migration'),
                recommendation=data.get('recommendation', 'unknown'),
                direction=data.get('direction', 'unknown'),
                generated_at_utc=generated_at or datetime.utcnow(),
                entry_price=data.get('entry_price'),
                stop_loss_price=data.get('stop_loss_price'),
                target_price=data.get('target_price'),
                score_blend=data.get('score_blend'),
                confidence=data.get('confidence'),
                risk_profile=data.get('risk_profile'),
                run_id=data.get('run_id'),
                rank_in_run=data.get('rank_in_run'),
                policy_version=data.get('policy_version'),
                features_json=data.get('features_json'),
                evaluated=bool(data.get('evaluated', 0)),
                evaluated_at_utc=evaluated_at,
                exit_price=data.get('exit_price'),
                exit_time_utc=exit_time,
                exit_reason=data.get('exit_reason'),
                pnl_pct=data.get('pnl_pct'),
                max_drawdown_pct=data.get('max_drawdown_pct'),
                alpha_vs_benchmark=data.get('alpha_vs_benchmark'),
                labels_json=data.get('labels_json'),
            )
            
            db.add(rec)
            migrated += 1
        
        db.commit()
        print(f"   ✅ Migrated {migrated} AI recommendations")
        
    except Exception as e:
        db.rollback()
        print(f"   ❌ Error migrating AI recommendations: {e}")
        raise
    finally:
        db.close()
        sqlite_conn.close()
    
    return migrated


def migrate_top_picks_runs():
    """Migrate top picks runs from SQLite to PostgreSQL"""
    print("\n🔄 Migrating Top Picks Runs...")
    
    sqlite_conn = sqlite3.connect('cache/top_picks_runs.db')
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()
    
    # Get all runs
    cursor.execute("SELECT * FROM top_picks_runs")
    rows = cursor.fetchall()
    
    if not rows:
        print("   ℹ️  No top picks runs to migrate")
        sqlite_conn.close()
        return 0
    
    db: Session = SessionLocal()
    migrated = 0
    
    try:
        for row in rows:
            # Convert SQLite row to dict
            data = dict(row)
            
            # Parse datetime
            created_at = None
            if data.get('created_at'):
                try:
                    created_at = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
                except:
                    created_at = datetime.utcnow()
            
            # Create PostgreSQL record
            run = TopPicksRun(
                run_id=data.get('run_id'),
                universe=data.get('universe', 'unknown'),
                mode=data.get('mode', 'unknown'),
                picks_json=data.get('picks_json', '[]'),
                elapsed_seconds=data.get('elapsed_seconds'),
                pick_count=data.get('pick_count'),
                created_at=created_at or datetime.utcnow(),
            )
            
            db.add(run)
            migrated += 1
        
        db.commit()
        print(f"   ✅ Migrated {migrated} top picks runs")
        
    except Exception as e:
        db.rollback()
        print(f"   ❌ Error migrating top picks runs: {e}")
        raise
    finally:
        db.close()
        sqlite_conn.close()
    
    return migrated


def main():
    """Run all migrations"""
    print("=" * 60)
    print("📦 SQLite to PostgreSQL Data Migration")
    print("=" * 60)
    
    total_migrated = 0
    
    try:
        # Migrate AI recommendations
        total_migrated += migrate_ai_recommendations()
        
        # Migrate top picks runs
        total_migrated += migrate_top_picks_runs()
        
        print("\n" + "=" * 60)
        print(f"✅ Migration Complete! Total records migrated: {total_migrated}")
        print("=" * 60)
        
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ Migration Failed: {e}")
        print("=" * 60)
        raise


if __name__ == "__main__":
    main()
