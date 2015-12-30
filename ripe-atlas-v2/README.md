# RIPE Atlas mPlane Proxy Version 2

This component provides access to RIPE Atlas through mPlane. It's possible to create and retrieve traceroute and ping measurements. Only a small-ish subset of the parameters are configurable, the rest uses default values.

## Installation

1. Obviously, you need the mPlane reference implementation (protocol-ri). The official repo is not supported yet.
2. You'll need the **ripe.atlas.cousteau** and the **ripe.atlas.sagan** packages, available on pip.
3. Copy the folder ripe-atlas-v2 (**not** only the contents) to [protocol-ri dir]/mplane/components.
4. Start the client and the component with the configuration files in this folder. Make sure the working directory is the topmost directory of your protocol-ri copy (i.e. where setup.py is). No supervisor necessary.
5. If you want to create measurements and get results from private measurements, you'll need to enter your key(s) in component.conf under the **module_ripe-atlas-v2** section.

## Usage

Most parameters and capability labels should be self-explanatory, but a few remarks are necessary:
- Only **IPv4** is supported
- You can specify a **point in the future** for `when` when retrieving results and the component will wait until that point, regardless if the measurement is already done.
- The service for retrieving results will always wait until **one minute** has passed since the end time before contacting RIPE Atlas.
- The service for creating a measurement will **return a receipt**, and the client automatically "redeems" that receipt at the service for retreiving results. If you really need the measurement ID, get it from the receipt or result of the second service.
- If you want a **one-off** measurement, just don't specify a duration. The interval has to be specified, but will be ignored. For example, `2015-12-12 12:00:00 / 1m` will will start a one-off measurement on the 12th of December 2015 at 12.
- When **creating measurements**, there are multiple options of how to select probes:
  - ripeatlas.probe_id: Zero or more probe IDs
  - ripeatlas.msm_id: Zero or more measurement IDs. All probes from those measurements will be reused.
  - ripeatlas.probe_source: A string for all other selection methods, consisting of pairs of token and number. As an example, `ASN42 3 34.56.76.12/8 100` will request three probes from AS with number 42 and 100 probes with the prefix `34.56.76.12/8`. See the table below for all options. This string can be empty.
  
Selection Method | Token Example (Case Sensitive)
------|-------
Area | One of WW, West, North-Central, South-Central, North-East, South-East
AS Number | ASN1234
IP Prefix | 1.2.3.4/16
Country | Any two-letter country code, like US or GB