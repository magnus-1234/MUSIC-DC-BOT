"""
Playlist Storage Module
Handles saving and loading music playlists in MongoDB.
Playlists are permanently stored in cloud — they survive bot restarts.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import List, Dict, Optional, Any

logger = logging.getLogger("music_bot.playlist_storage")

# Try to import MongoDB support (Motor for async)
try:
    from motor.motor_asyncio import AsyncIOMotorClient
    MONGO_AVAILABLE = True
except ImportError:
    MONGO_AVAILABLE = False


class PlaylistStorage:
    """Manages playlist persistence in a dedicated MongoDB collection.
    
    Playlists are stored permanently in MongoDB — they are never lost on restart.
    Users can save playlists via Discord commands or the web dashboard.
    """

    def __init__(self):
        self.mongo_client = None
        self.mongo_db = None
        self.mongo_enabled = False
        self.initialized = False
        self.collection_name = os.getenv('MUSIC_PLAYLIST_COLLECTION', 'music_playlists')
        logger.info("Playlist storage module loaded")

    async def initialize(self):
        """Async initialization — connects to MongoDB. Non-fatal on failure."""
        if self.initialized:
            return

        logger.info("Initializing playlist storage...")

        if not MONGO_AVAILABLE:
            logger.warning("motor package not installed — MongoDB unavailable. Playlists will not be saved.")
            self.initialized = True
            return

        primary_uri = os.getenv('MONGO_URI')
        fallback_uri = os.getenv('MONGO_URI_FALLBACK')

        uris_to_try = []
        if primary_uri:
            uris_to_try.append(('primary', primary_uri))
        if fallback_uri and fallback_uri != primary_uri:
            uris_to_try.append(('fallback', fallback_uri))

        if not uris_to_try:
            logger.warning("No MONGO_URI configured — playlists will not persist across restarts.")
            self.initialized = True
            return

        for uri_label, uri in uris_to_try:
            try:
                logger.info("Connecting to %s MongoDB...", uri_label)
                self.mongo_client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=8000)
                db_name = os.getenv('MONGO_DB_NAME', 'discord_bot')
                self.mongo_db = self.mongo_client[db_name]

                # Test connection
                await self.mongo_client.admin.command('ping')

                # Ensure indexes
                collection = self.mongo_db[self.collection_name]
                await collection.create_index(
                    [('guild_id', 1), ('user_id', 1), ('name', 1)],
                    unique=True,
                    name='guild_user_playlist_unique'
                )
                await collection.create_index(
                    [('user_id', 1), ('updated_at', -1)],
                    name='user_updated_at'
                )

                count = await collection.count_documents({})
                self.mongo_enabled = True
                logger.info("Connected to %s MongoDB (%s). %d playlist(s) in cloud storage.", uri_label, db_name, count)
                break

            except Exception as e:
                logger.warning("MongoDB (%s) connection failed: %s", uri_label, e)
                self.mongo_enabled = False
                self.mongo_client = None
                self.mongo_db = None

        if not self.mongo_enabled:
            logger.warning("All MongoDB connections failed — playlists will not persist. Bot will still work normally.")

        self.initialized = True
        logger.info("Playlist storage initialization complete.")

    async def save_playlist(self, guild_id: int, user_id: int, name: str, tracks: List[Dict[str, Any]]) -> bool:
        """Save (or update) a playlist permanently in MongoDB.
        
        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID  
            name: Playlist name
            tracks: List of track dicts with keys: title, author, uri, length
            
        Returns:
            True if saved successfully, False otherwise
        """
        if not self.mongo_enabled:
            logger.warning("Cannot save playlist — MongoDB not connected.")
            return False

        now = datetime.utcnow().isoformat()
        try:
            collection = self.mongo_db[self.collection_name]
            await collection.update_one(
                {'guild_id': guild_id, 'user_id': user_id, 'name': name},
                {
                    '$set': {'tracks': tracks, 'updated_at': now},
                    '$setOnInsert': {'created_at': now}
                },
                upsert=True
            )
            logger.info("Saved playlist '%s' for user %s in guild %s (%d tracks)", name, user_id, guild_id, len(tracks))
            return True
        except Exception as e:
            logger.error("MongoDB save error: %s", e)
            return False

    async def load_playlist(self, guild_id: int, user_id: int, name: str) -> Optional[Dict[str, Any]]:
        """Load a specific playlist by name."""
        if not self.mongo_enabled:
            return None
        try:
            collection = self.mongo_db[self.collection_name]
            doc = await collection.find_one({'guild_id': guild_id, 'user_id': user_id, 'name': name})
            if doc:
                return {
                    'name': doc['name'],
                    'tracks': doc.get('tracks', []),
                    'created_at': doc.get('created_at', ''),
                    'updated_at': doc.get('updated_at', ''),
                }
            return None
        except Exception as e:
            logger.error("MongoDB load error: %s", e)
            return None

    async def list_playlists(self, guild_id: int, user_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List all playlists for a user in a guild, including full track data."""
        if not self.mongo_enabled:
            return []
        try:
            collection = self.mongo_db[self.collection_name]
            cursor = collection.find(
                {'guild_id': guild_id, 'user_id': user_id}
            ).sort('updated_at', -1).skip(offset).limit(limit)

            playlists = []
            async for doc in cursor:
                tracks = doc.get('tracks', [])
                playlists.append({
                    'name': doc['name'],
                    'guildId': str(guild_id),
                    'userId': str(user_id),
                    'trackCount': len(tracks),
                    'tracks': tracks,
                    'created_at': doc.get('created_at', ''),
                    'updated_at': doc.get('updated_at', ''),
                })
            return playlists
        except Exception as e:
            logger.error("MongoDB list error: %s", e)
            return []

    async def list_playlists_for_user(self, user_id: int, limit: int = 200) -> List[Dict[str, Any]]:
        """List all playlists for a user across all guilds (for the web dashboard)."""
        if not self.mongo_enabled:
            return []
        try:
            collection = self.mongo_db[self.collection_name]
            cursor = collection.find({'user_id': user_id}).sort('updated_at', -1).limit(limit)

            playlists = []
            async for doc in cursor:
                tracks = doc.get('tracks', [])
                playlists.append({
                    'name': doc['name'],
                    'guildId': str(doc.get('guild_id', '')),
                    'userId': str(user_id),
                    'trackCount': len(tracks),
                    'tracks': tracks,
                    'createdAt': doc.get('created_at', ''),
                    'updatedAt': doc.get('updated_at', ''),
                })
            return playlists
        except Exception as e:
            logger.error("MongoDB list_for_user error: %s", e)
            return []

    async def delete_playlist(self, guild_id: int, user_id: int, name: str) -> bool:
        """Delete a playlist permanently."""
        if not self.mongo_enabled:
            return False
        try:
            collection = self.mongo_db[self.collection_name]
            result = await collection.delete_one({'guild_id': guild_id, 'user_id': user_id, 'name': name})
            return result.deleted_count > 0
        except Exception as e:
            logger.error("MongoDB delete error: %s", e)
            return False

    async def count_playlists(self, guild_id: int, user_id: int) -> int:
        """Count playlists for a user in a guild."""
        if not self.mongo_enabled:
            return 0
        try:
            collection = self.mongo_db[self.collection_name]
            return await collection.count_documents({'guild_id': guild_id, 'user_id': user_id})
        except Exception as e:
            logger.error("MongoDB count error: %s", e)
            return 0


# Global singleton instance
playlist_storage = PlaylistStorage()
