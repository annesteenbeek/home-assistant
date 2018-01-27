"""Provide a registry to track entities."""
import asyncio
from collections import namedtuple, OrderedDict
from datetime import timedelta
import os

from ..core import callback, split_entity_id
from ..helpers.event import async_track_point_in_utc_time
from ..util.yaml import load_yaml, save_yaml
from ..util.dt import utcnow
from .entity import async_generate_entity_id

PATH_REGISTRY = 'entity_registry.yaml'
SAVE_DELAY = 10
Entry = namedtuple('EntityRegistryEntry',
                   'entity_id,unique_id,platform,domain')


class EntityRegistry:
    """Class to hold a registry of entities."""

    def __init__(self, hass):
        """Initialize the registry."""
        self.hass = hass
        self.entities = None
        self._load_task = None
        self._sched_save = None

    @callback
    def async_get_or_create(self, domain, platform, unique_id, name=None):
        """Get entity. Creat if it doesn't exist."""
        for entity in self.entities.values():
            if entity.domain == domain and entity.platform == platform and \
               entity.unique_id == unique_id:
                return entity

        entity_id = async_generate_entity_id(
            domain + '.{}', name or unique_id, self.entities.keys())

        entity = Entry(
            entity_id=entity_id,
            unique_id=unique_id,
            platform=platform,
            domain=domain,
        )
        self.entities[entity_id] = entity
        self.async_schedule_save()
        return entity

    @asyncio.coroutine
    def async_ensure_loaded(self):
        """Load the registry from disk."""
        if self.entities is not None:
            return

        if self._load_task is None:
            self._load_task = self.hass.async_add_job(self._async_load)

        yield from self._load_task

    @asyncio.coroutine
    def _async_load(self):
        """Load the entity registry."""
        path = self.hass.config.path(PATH_REGISTRY)
        entities = OrderedDict()

        if os.path.isfile(path):
            data = yield from self.hass.async_add_job(load_yaml, path)

            for entity_id, info in data.items():
                entities[entity_id] = Entry(
                    domain=split_entity_id(entity_id)[0],
                    entity_id=entity_id,
                    unique_id=info['unique_id'],
                    platform=info['platform']
                )

        self.entities = entities
        self._load_task = None

    @callback
    def async_schedule_save(self):
        """Schedule saving the entity registry."""
        if self._sched_save is not None:
            self._sched_save.cancel()

        self._sched_save = self.hass.loop.call_later(
            SAVE_DELAY,  self.hass.async_add_job, self._async_save
        )

    @asyncio.coroutine
    def _async_save(self, _):
        """Save the entity registry to a file."""
        self._sched_save = None
        data = OrderedDict()

        for entry in self.entities.values():
            data[entry.entity_id] = {
                'unique_id': entry.unique_id,
                'platform': entry.platform,
            }

        yield from self.hass.async_add_job(
            save_yaml, self.hass.config.path(PATH_REGISTRY), data)
