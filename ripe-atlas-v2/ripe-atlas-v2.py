import mplane.model
import mplane.scheduler
import ripe.atlas.cousteau as cousteau
import ripe.atlas.sagan as sagan
from datetime import datetime
from time import sleep
import pytz
import re

_API_key = ""

def services(API_key):
    _API_key = API_key
    services = []
    services.append(AtlasResultService(result_common_cap(result_ping_cap())))
    services.append(AtlasResultService(result_common_cap(result_trace_cap())))
    services.append(AtlasCreateService(create_common_cap(create_ping_cap())))
    services.append(AtlasCreateService(create_common_cap(create_trace_cap())))
    return services

def result_ping_cap():
    cap = mplane.model.Capability(verb = mplane.model.VERB_MEASURE, label = "ripeatlas-ping-result", when = "past ... future")
    cap.add_result_column("delay.twoway.icmp.us.min")
    cap.add_result_column("delay.twoway.icmp.us.mean")
    cap.add_result_column("delay.twoway.icmp.us.50pct")
    cap.add_result_column("delay.twoway.icmp.us.max")
    cap.add_result_column("delay.twoway.icmp.count")
    return cap

def result_trace_cap():
    cap = mplane.model.Capability(verb = mplane.model.VERB_MEASURE, label = "ripeatlas-trace-result", when = "past ... future")
    cap.add_result_column("intermediate.ip4")
    cap.add_result_column("ripeatlas.traceroute_id")
    cap.add_result_column("ripeatlas.hop_index")
    cap.add_result_column("ripeatlas.paris_id")
    cap.add_result_column("ripeatlas.protocol")
    cap.add_result_column("hops.ip")
    cap.add_result_column("rtt.ms")
    return cap

def result_common_cap(cap):
    cap.add_parameter("ripeatlas.msm_id")
    cap.add_result_column("source.ip4")
    cap.add_result_column("destination.ip4")
    cap.add_result_column("ripeatlas.probe_id")
    cap.add_result_column("time")
    return cap

def create_ping_cap():
    cap = mplane.model.Capability(verb = mplane.model.VERB_QUERY, label = "ripeatlas-ping-create", when = "now ... future / 1s")
    return cap

def create_trace_cap():
    cap = mplane.model.Capability(verb = mplane.model.VERB_QUERY, label = "ripeatlas-trace-create", when = "now ... future / 1s")
    cap.add_parameter("ripeatlas.protocol", "ICMP,TCP,UDP")
    cap.add_parameter("ripeatlas.paris", "0 ... 64")
    return cap

def create_common_cap(cap):
    cap.add_parameter("ripeatlas.probe_id", "[*]")
    cap.add_parameter("ripeatlas.msm_id", "[*]")
    cap.add_parameter("ripeatlas.probe_source")
    cap.add_parameter("ripeatlas.description")
    cap.add_parameter("destination.ip4")
    cap.add_result_column("ripeatlas.msm_id")
    return cap

class AtlasResultService(mplane.scheduler.Service):
    def __init__(self, capability):
        return super().__init__(capability)

    def _notnone(self, value, default):
        if value is not None and value is not "":
            return value
        else:
            return default

    def run(self, spec, check_interrupt):
        starttime, endtime = spec.when().datetimes()
        res = mplane.model.Result(specification=spec)

        #wait until the measurement ended or at least started
        waittime = endtime if endtime is not None else starttime;
        while datetime.utcnow() < waittime:
            if check_interrupt():
                res.set_when(mplane.model.When(a = starttime, b = endtime))
                return res
            sleep(1)

        msm_id = spec.get_parameter_value("ripeatlas.msm_id")
        kwargs = {
            "msm_id": msm_id,
            "start": starttime,
            "end": endtime,
            "key": _API_key
        }
        is_success, reqanswer = cousteau.AtlasResultsRequest(**kwargs).create();
        if not is_success:
            raise RuntimeError("AtlasResultsRequest was not successful: " + str(reqanswer["detail"]))
        measstart = datetime.now(tz=pytz.UTC)
        measend = datetime.fromtimestamp(0, pytz.UTC)
        print("Got " + str(len(reqanswer)) + " results. Processing...")
        #
        #       PING MEASUREMENT
        #
        if  "ripeatlas-ping-result" in spec.get_label():
            if not cousteau.Measurement(id=msm_id).type == "PING":
                raise ValueError("Measurement " + str(msm_id) + " ist not of type ping")
            i = 0
            for proberes in reqanswer:
                result = sagan.PingResult(proberes)
                if result.is_malformed or result.is_error:
                   continue
                res.set_result_value("delay.twoway.icmp.us.min", self._notnone(result.rtt_min, 0) * 1000, i)
                res.set_result_value("delay.twoway.icmp.us.mean", self._notnone(result.rtt_average, 0) * 1000, i)
                res.set_result_value("delay.twoway.icmp.us.50pct", self._notnone(result.rtt_median, 0) * 1000, i)
                res.set_result_value("delay.twoway.icmp.us.max", self._notnone(result.rtt_max, 0) * 1000, i)
                res.set_result_value("delay.twoway.icmp.count", self._notnone(result.packets_received, 0), i)
                res.set_result_value("source.ip4", self._notnone(result.origin, "0.0.0.0"), i)
                res.set_result_value("destination.ip4",self._notnone(result.destination_address, "0.0.0.0"), i)
                res.set_result_value("ripeatlas.probe_id", result.probe_id, i)
                res.set_result_value("time", mplane.model.When(a=result.created), i)
                measstart = result.created if result.created < measstart else measstart
                measend = result.created if result.created > measend else measend
                i += 1

        #
        #       TRACEROUTE MEASUREMENT
        #
        elif "ripeatlas-trace-result" in spec.get_label():
            if not cousteau.Measurement(id=msm_id).type == "TRACEROUTE":
                raise ValueError("Measurement " + str(msm_id) + " ist not of type traceroute")
            i = 0
            for proberes in reqanswer:
                result = sagan.TracerouteResult(proberes)
                if result.is_malformed or result.is_error:
                    continue
                for hopindex, hop in enumerate(result.hops):
                    if hop.is_malformed or hop.is_error:
                        continue
                    for packet in hop.packets:
                        if packet.is_malformed or packet.is_error:
                           continue
                        res.set_result_value("intermediate.ip4", self._notnone(packet.origin, "0.0.0.0"), i)
                        res.set_result_value("ripeatlas.traceroute_id", hash(str(result.created) + result.origin), i)
                        res.set_result_value("ripeatlas.hop_index", hopindex, i)
                        res.set_result_value("ripeatlas.paris_id", self._notnone(result.paris_id, -1), i)
                        res.set_result_value("ripeatlas.protocol", self._notnone(result.protocol, ""), i)
                        res.set_result_value("hops.ip", self._notnone(result.total_hops, 0), i)
                        res.set_result_value("rtt.ms", self._notnone(packet.rtt, 0), i)
                        res.set_result_value("source.ip4", self._notnone(result.origin, "0.0.0.0"), i)
                        res.set_result_value("destination.ip4", self._notnone(result.destination_address, "0.0.0.0"), i)
                        res.set_result_value("ripeatlas.probe_id", result.probe_id, i)
                        res.set_result_value("time", mplane.model.When(a=result.created), i)
                        i += 1
                measstart = result.created if result.created < measstart else measstart
                measend = result.created if result.created > measend else measend
        else:
            raise ValueError("Unknown specification label: " + spec.get_label())

        #fix times if there are no results
        if res.count_result_rows() is 0:
            measstart, measend = spec.when().datetimes()

        res.set_when(mplane.model.When(a = measstart, b = measend))
        print("Sending " + str(res.count_result_rows()) + " result rows. This might take a while.")
        return res

class AtlasCreateService(mplane.scheduler.Service):
    def __init__(self, capability):
        return super().__init__(capability)

    def _parse_source(self, spec):
        sources = []
        tags = {"include": ["system-ipv4-works"]}
        areas = ["WW", "West", "North-Central", "South-Central", "North-East", "South-East"]

        probeids = spec.get_parameter_value("ripeatlas.probe_id")
        if len(probeids) > 0:
            sources.append(cousteau.AtlasSource(type="probes", value=",".join([str(id) for id in probeids]), requested=len(probeids),
                                                tags = tags))

        msmids = spec.get_parameter_value("ripeatlas.msm_id")
        if len(msmids) > 0:
            for msm in msmids:
                #TODO: get amount of probes from measurement
                sources.append(cousteau.AtlasSource(type="msm", value=str(msm), requested=1, tags = tags))

        vals = spec.get_parameter_value("ripeatlas.probe_source").split()
        if len(vals) % 2 is not 0:
            raise ValueError("Expected even amount of values in ripeatlas.probe_source (got " + str(len(vals)) + ")")
        #Iterate over every two strings
        for stype, samount in zip(*[iter(vals)]*2):
            if int(samount) == 0:
                continue

            if stype in areas: #e.g. "WW 2"
                sources.append(cousteau.AtlasSource(type="area", value=stype, requested=int(samount), tags = tags))
            elif stype[0:3] == "ASN": #e.g. "ASN3333 42"
                sources.append(cousteau.AtlasSource(type="asn", value=stype[3:], requested=int(samount), tags = tags))
            elif re.match(r"([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$", stype): #e.g. "193.3.6.0/8 4"
                #Note: regex doesn't check bounds
                sources.append(cousteau.AtlasSource(type="prefix", value=stype, requested=int(samount), tags = tags))
            elif len(stype) is 2: #e.g. "CH 1337"
                #TODO: should probably check if the country code is valid
                sources.append(cousteau.AtlasSource(type="country", value=stype, requested=int(samount), tags = tags))
            else:
                print("Warning: Unknown type " + stype + " when parsing ripeatlas.probe_source")

        return sources
    
    def run(self, spec, check_interrupt):
        measurement = cousteau.measurement.AtlasMeasurement()
        res = mplane.model.Specification()
        sources = self._parse_source(spec)
        desc = spec.get_parameter_value("ripeatlas.description")
        if len(sources) is 0:
            raise ValueError("No probes for this measurement have been defined")
        #
        #       PING MEASUREMENT
        #
        if  "ripeatlas-ping-create" in spec.get_label():
            if desc == "":
                desc = "Ping to " + str(spec.get_parameter_value("destination.ip4"))
            res = mplane.model.Specification(capability = result_common_cap(result_ping_cap()))
            measurement = cousteau.Ping(af = 4, target = str(spec.get_parameter_value("destination.ip4")),
                                        description = desc, interval = spec.when().period().seconds);
            
        #
        #       TRACEROUTE MEASUREMENT
        #
        elif "ripeatlas-trace-create" in spec.get_label():
            if desc == "":
                desc = spec.get_parameter_value("ripeatlas.protocol") + " traceroute to " + str(spec.get_parameter_value("destination.ip4"))
            res = mplane.model.Specification(capability = result_common_cap(result_trace_cap()))
            measurement = cousteau.Traceroute(af = 4, target = str(spec.get_parameter_value("destination.ip4")),
                                        description = "test", interval = spec.when().period().seconds,
                                        paris = spec.get_parameter_value("ripeatlas.paris"),
                                        protocol = spec.get_parameter_value("ripeatlas.protocol"));
        else:
            raise ValueError("Unknown specification label: " + spec.get_label())


        start, end = spec.when().datetimes()
        request = cousteau.AtlasCreateRequest(key = _API_key, measurements = [measurement], sources = sources,
                                              start_time = start, stop_time = end);
        (is_success, response) = request.create()
        if not is_success:
            raise RuntimeError("AtlasCreateRequest was not successful: " + str(response["detail"]))

        res.set_parameter_value("ripeatlas.msm_id", response["measurements"][0])
        res.set_when(spec.when())
        res = mplane.model.Receipt(specification = res)
        return res