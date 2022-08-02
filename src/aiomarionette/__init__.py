'''Firefox Marionette protocol for asyncio

This module provides an asynchronous implementation of the Firefox
Marionette protocol over TCP sockets.

>>> async with Marionette() as mn:
...     await mn.connect()
...     await mn.navigate('https://getfirefox.com/')
'''

import dataclasses
import abc
import asyncio
import json
import logging
import random
import socket
from types import TracebackType
from typing import Any, Dict, List, Literal, Optional, Type, Union, cast


log = logging.getLogger(__name__)


WindowType = Union[Literal['window'], Literal['tab']]


@dataclasses.dataclass
class WindowRect:
    '''Window size and location'''

    x: int
    '''Position x coordinate in pixels'''
    y: int
    '''Position y coordinate in pixels'''
    height: int
    '''Height in pixels'''
    width: int
    '''Width in pixels'''


class MarionetteException(Exception):
    '''Base class for Marionette errors'''


class _BaseRPC(metaclass=abc.ABCMeta):
    # pylint: disable=too-few-public-methods

    @abc.abstractmethod
    async def _send_message(self, command: str, **kwargs: Any) -> Any:
        ...


class WebDriverBase(_BaseRPC, metaclass=abc.ABCMeta):
    '''WebDriver protocol implementation'''

    async def close_window(self) -> List[str]:
        '''Close the current window

        If the last window is closed, the session will be ended.

        :returns: List of handles of remaining windows
        '''

        windows: List[str] = await self._send_message('WebDriver:CloseWindow')
        return windows

    async def fullscreen(self) -> WindowRect:
        '''Enter or exit fullscreen for the current window

        :returns: New :py:class:`WindowRect` with current size/location
        '''

        res: WindowRect = await self._send_message(
            'WebDriver:FullscreenWindow'
        )
        return res

    async def get_title(self) -> str:
        '''Get the current window title'''

        res = await self._send_message('WebDriver:GetTitle')
        title: str = res['value']
        return title

    async def get_url(self) -> str:
        '''Get the URL of the current window'''

        res = await self._send_message('WebDriver:GetCurrentURL')
        url: str = res['value']
        return url

    async def get_window_rect(self) -> WindowRect:
        '''Get the current window position and dimensions'''

        res: Dict[str, int] = await self._send_message(
            'WebDriver:GetWindowRect'
        )
        return WindowRect(**res)

    async def get_window_handles(self) -> List[str]:
        '''Get a list of handles for all open windows'''

        handles: List[str]
        handles = await self._send_message('WebDriver:GetWindowHandles')
        return handles

    async def navigate(self, url: str) -> None:
        '''Navigate to the specified location'''

        await self._send_message('WebDriver:Navigate', url=url)

    async def new_window(
        self,
        type: Optional[WindowType] = None,  # pylint: disable=redefined-builtin
        focus: bool = False,
        private: bool = False,
    ) -> str:
        '''Open a new window or tab

        :param type: Either ``'window'`` or ``'tab'``
        :param focus: Give the new window focus
        :param private: Open a new private window
        '''

        res = await self._send_message(
            'WebDriver:NewWindow',
            type=type,
            focus=focus,
            private=private,
        )
        handle: str = res['handle']
        return handle

    async def set_window_rect(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        height: Optional[int] = None,
        width: Optional[int] = None,
    ) -> WindowRect:
        '''Resize the current window

        :param x: Position x coordinate in pixels
        :param y: Position y coordinate in pixels
        :param height: Height in pixels
        :param width: Width in pixels
        '''

        if (x is None and y is None) and (height is None and width is None):
            raise ValueError('x and y OR height and width need values')
        res: Dict[str, int] = await self._send_message(
            'WebDriver:SetWindowRect',
            x=x,
            y=y,
            height=height,
            width=width,
        )
        return WindowRect(**res)

    async def refresh(self) -> None:
        '''Refresh the current window content'''

        await self._send_message('WebDriver:Refresh')

    async def switch_to_window(self, handle: str, focus: bool = True) -> None:
        '''Switch to the specified window

        :param handle: Window handle
        :param focus: Give the selected window focus
        '''

        await self._send_message(
            'WebDriver:SwitchToWindow', handle=handle, focus=focus
        )

    async def take_screenshot(
        self,
        *,
        hash: bool = False,  # pylint: disable=redefined-builtin
        full: bool = True,
        scroll: bool = True,
    ) -> str:
        '''Take a screenshot of the current frame

        :returns: Lossless PNG image encoded as a base-64 Unicode string
        '''

        res: Dict[str, str] = await self._send_message(
            'WebDriver:TakeScreenshot',
            full=full,
            hash=hash,
            scroll=scroll,
        )
        return res['value']


class Marionette(WebDriverBase):
    '''Firefox Marionette session

    This class implements the WebDriver protocol; see
    :py:class:`WebDriverBase` for available methods.
    '''

    def __init__(self, host: str = 'localhost', port: int = 2828) -> None:
        self.host = host
        '''Socket host'''
        self.port = port
        '''Socket port'''
        self._transport: Optional[asyncio.Transport] = None
        self._waiting: Dict[int, asyncio.Future[Any]] = {}
        self.session: Optional[Dict[str, Any]] = None
        '''Marionette session information'''

    async def __aenter__(self) -> 'Marionette':
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[Exception]],
        exc_value: Optional[Exception],
        tb: Optional[TracebackType],
    ) -> None:
        await self.close()

    async def close(self) -> None:
        '''Close the connection'''

        self._waiting.clear()
        if self._transport is not None:
            self._transport.close()
        self._transport = None
        self.session = None

    async def connect(self) -> None:
        '''Connect to the Marionette socket and begin a session'''

        hello = await self._connect()
        log.info(
            'Connected to Marionette server '
            '(protocol: %s, application type: %s)',
            hello.get('marionetteProtocol'),
            hello.get('applicationType'),
        )
        self.session = await self._send_message(
            'WebDriver:NewSession', strictFileInteractibility=True
        )

    async def _connect(self) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        while 1:
            log.info(
                'Connecting to Marionette server %s on port %d',
                self.host,
                self.port,
            )
            try:
                res = await loop.getaddrinfo(
                    self.host, self.port, type=socket.SOCK_STREAM
                )
                if res:
                    family = res[0][0]
                    host, port = res[0][4][:2]
                else:
                    host = self.host
                    port = self.port
                    family = socket.AF_INET
                transport, _protocol = await loop.create_connection(
                    lambda: _MarionetteProtocol(self),
                    host=host,
                    port=port,
                    family=family,
                )
                fut = self._waiting[-1] = loop.create_future()
                hello: Dict[str, Any] = await fut
            except (OSError, EOFError) as e:
                log.error('Failed to connect to Marionette server: %s', e)
                await asyncio.sleep(1)
                continue
            else:
                self._transport = cast(asyncio.Transport, transport)
                break
        # pyright: reportUnboundVariable=false
        return hello

    async def _send_message(self, command: str, **kwargs: Any) -> Any:
        assert self._transport
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        msgid = random.randint(0, 65535)
        msg = json.dumps([0, msgid, command, kwargs or None])
        log.debug('Sending message: %r', msg)
        self._transport.write(f'{len(msg)}:{msg}'.encode('utf-8'))
        self._waiting[msgid] = fut
        return await fut

    def _message_received(self, data: bytes) -> None:
        try:
            message = json.loads(data)
        except ValueError as e:
            log.error('Got invalid message from Marionette server: %s', e)
            return
        if -1 in self._waiting:
            self._waiting.pop(-1).set_result(message)
        if isinstance(message, list):
            if message[0] != 1:
                log.error('Unsupported message type: %r', message[0])
                return
            try:
                fut = self._waiting.pop(message[1])
            except KeyError:
                log.warning(
                    'Nothing waiting for response to message ID %s', message[1]
                )
                return
            if message[2] is not None:
                fut.set_exception(MarionetteException(message[2]))
            else:
                fut.set_result(message[3])

    def _connection_error(self, exc: Exception) -> None:
        while self._waiting:
            _msgid, fut = self._waiting.popitem()
            fut.set_exception(exc)


class _MarionetteProtocol(asyncio.Protocol):
    def __init__(self, marionette: Marionette) -> None:
        self.marionette = marionette
        self.buf = bytearray()

    def data_received(self, data: bytes) -> None:
        self.buf += data
        while self.buf:
            try:
                idx = self.buf.index(b':')
            except ValueError:
                return
            length = int(self.buf[:idx])
            end = idx + 1 + length
            if len(self.buf) < end:
                return
            end = idx + 1 + length
            data = self.buf[idx + 1 : end]
            self.buf = self.buf[end:]
            log.debug('Received message: %s', data)
            # pylint: disable=protected-access
            self.marionette._message_received(data)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        log.error('Connection lost, cancelling outstanding requests')
        if exc is None:
            exc = EOFError()
        # pylint: disable=protected-access
        self.marionette._connection_error(exc)
