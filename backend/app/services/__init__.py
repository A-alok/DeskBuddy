"""Domain logic.

Services are synchronous and only touch the database. Broadcasting is the
caller's job (routers, WebSocket handlers, the scheduler) so that persistence
and fan-out stay independently testable.
"""
