# FireFox Marionette Client for *asyncio*

*aiomarionette* provides an asynchronous client interface for the [Firefox
Marionette] remote control protocol.

[Firefox Marionette]: https://firefox-source-docs.mozilla.org/testing/marionette/index.html

## Usage

To use *aiomarionette*, create an instance of the `Marionette` class.  By
default, the cclient will attempt to connect to the Marionette socket on the
local machine, port 2828.  You can specify the `host` and/or `port` arguments to
change this.  Be sure to call the `connect` method first, before calling any
of the command methods.

```python
async with aiomarionette.Marionette() as mn:
    mn.connect()
    mn.navigate('https://getfirefox.com/')
```

## Compared to *marionette_driver*

The official Python client for Firefox Marionette is [marionette_driver].
Although it is more complete than *aiomarionette* (at least for now), it only
provides a blocking API.

Unlike *marionette_driver*, *aiomarionette* does not currently support launching
Firefox directly.  You must explicity start a Firefox process in Marionette mode
before connecting to it with *aiomarionette*.

[marionette_driver]: https://pypi.org/project/marionette-driver/
