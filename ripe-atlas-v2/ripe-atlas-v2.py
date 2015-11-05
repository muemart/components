import mplane.model
import mplane.scheduler
import ripe.atlas.cousteau as cousteau
import ripe.atlas.sagan as sagan
from datetime import datetime
import pytz

_API_key = ""

def services(API_key):
    _API_key = API_key
    services = []
    services.append(AtlasResultService(result_common_cap(result_ping_cap())))
    services.append(AtlasResultService(result_common_cap(result_trace_cap())))
    services.append(AtlasCreateService(create_common_cap(create_ping_cap())))
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

def create_common_cap(cap):
    cap.add_parameter("ripeatlas.probe_id", "[*]")
    cap.add_parameter("destination.ip4")
    cap.add_result_column("ripeatlas.msm_id")
    return cap

class AtlasResultService(mplane.scheduler.Service):
    def __init__(self, capability):
        return super().__init__(capability)

    def _notnone(self, value, default):
        if value is not None:
            return value
        else:
            return default

    def run(self, spec, check_interrupt):
        starttime, endtime = spec.when().datetimes()
        msm_id = spec.get_parameter_value("ripeatlas.msm_id")
        kwargs = {
            "msm_id": msm_id,
            "start": starttime,
            "end": endtime,
            "key": _API_key
        }
        is_success, reqanswer = cousteau.AtlasResultsRequest(**kwargs).create();
        if not is_success:
            raise RuntimeError("AtlasResultsRequest was not successful: " + str(reqanswer))
        res = mplane.model.Result(specification=spec)
        measstart = datetime.now(tz=pytz.UTC)
        measend = datetime.fromtimestamp(0, pytz.UTC)

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
                    hopindex = 0
                    if hop.is_malformed or hop.is_error:
                        continue
                    for packet in hop.packets:
                        if packet.is_malformed or packet.is_error:
                           continue
                        res.set_result_value("intermediate.ip4", self._notnone(packet.origin, "0.0.0.0"),i)
                        res.set_result_value("ripeatlas.traceroute_id", hash(str(result.created) + result.origin),i)
                        res.set_result_value("ripeatlas.hop_index", hopindex)
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

        res.set_when(mplane.model.When(a = measstart, b = measend))
        print("Sending " + str(res.count_result_rows()) + " result rows. This might take a while.")
        return res

class AtlasCreateService(mplane.scheduler.Service):
    def __init__(self, capability):
        return super().__init__(capability)
    
    def run(self, spec, check_interrupt):
        probeids = spec.get_parameter_value("ripeatlas.probe_id")
        source = cousteau.AtlasSource(type="probes", value=",".join([str(id) for id in probeids]), requested=len(probeids))
        measurement = cousteau.measurement.AtlasMeasurement()
        if  "ripeatlas-ping-create" in spec.get_label():
            measurement = cousteau.Ping(af = 4, target = str(spec.get_parameter_value("destination.ip4")),
                                        description = "test", interval = spec.when().period().seconds);

        start, end = spec.when().datetimes()
        request = cousteau.AtlasCreateRequest(key = _API_key, measurements = [measurement], sources = [source],
                                              start_time = start, stop_time = end);
        #(is_success, response) = request.create()
        #if not is_success:
        #    raise RuntimeError("AtlasCreateRequest was not successful: " + str(response))
        
        #res = mplane.model.Result(specification=spec)
        #res.set_result_value("ripeatlas.msm_id", response["measurements"][0])
        res = mplane.model.Specification(capability = result_common_cap(result_ping_cap()))
        res.set_parameter_value("ripeatlas.msm_id", 1)
        res.set_when(spec.when())
        res = mplane.model.Receipt(specification = res)
        return res