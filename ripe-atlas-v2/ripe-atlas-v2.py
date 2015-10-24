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
    cap = mplane.model.Capability(verb = mplane.model.VERB_QUERY, label = "ripeatlas-ping-result", when = "past ... now")
    cap.add_result_column("delay.twoway.icmp.us.min")
    cap.add_result_column("delay.twoway.icmp.us.mean")
    cap.add_result_column("delay.twoway.icmp.us.50pct")
    cap.add_result_column("delay.twoway.icmp.us.max")
    cap.add_result_column("delay.twoway.icmp.count")
    return cap

def result_trace_cap():
    cap = mplane.model.Capability(verb = mplane.model.VERB_QUERY, label = "ripeatlas-trace-result", when = "past ... now")
    cap.add_result_column("intermediate.ip4")
    cap.add_result_column("ripeatlas.traceroute_id")
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
    cap = mplane.model.Capability(label = "ripeatlas-ping-create", when = "now ... future / 1s")
    return cap

def create_common_cap(cap):
    cap.add_parameter("ripeatlas.probe_id", "[*]")
    cap.add_parameter("destination.ip4")
    cap.add_result_column("ripeatlas.msm_id")
    return cap

class AtlasResultService(mplane.scheduler.Service):
    def __init__(self, capability):
        return super().__init__(capability)

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
        if  "ripeatlas-ping-result" in spec.get_label():
            if not cousteau.Measurement(id=msm_id).type == "ping":
                raise ValueError("Measurement " + str(msm_id) + " ist not of type ping")
            for i, proberes in enumerate(reqanswer):
                result = sagan.PingResult(proberes)
                res.set_result_value("delay.twoway.icmp.us.min", result.rtt_min * 1000, i)
                res.set_result_value("delay.twoway.icmp.us.mean", result.rtt_average * 1000, i)
                res.set_result_value("delay.twoway.icmp.us.50pct", result.rtt_median * 1000, i)
                res.set_result_value("delay.twoway.icmp.us.max", result.rtt_max * 1000, i)
                res.set_result_value("delay.twoway.icmp.count", result.packets_received, i)
                res.set_result_value("source.ip4",result.origin,i)
                res.set_result_value("destination.ip4",result.destination_address,i)
                res.set_result_value("ripeatlas.probe_id", result.probe_id, i)
                res.set_result_value("time", mplane.model.When(a=result.created), i)
                measstart = result.created if result.created < measstart else measstart
                measend = result.created if result.created > measend else measend
        elif "ripeatlas-trace-result" in spec.get_label():
            if not cousteau.Measurement(id=msm_id).type == "traceroute":
                raise ValueError("Measurement " + str(msm_id) + " ist not of type traceroute")
            i = 0
            for proberes in reqanswer:
                result = sagan.TracerouteResult(proberes)
                for hop in result.hops:
                    if hop.packets[0].origin == "" or result.origin == "":
                        continue
                    #Just take the IP address of the first packet for now
                    res.set_result_value("intermediate.ip4", hop.packets[0].origin,i)
                    res.set_result_value("ripeatlas.traceroute_id", hash(str(result.created) + result.origin),i)
                    res.set_result_value("hops.ip",result.total_hops,i)
                    res.set_result_value("rtt.ms",result.last_median_rtt,i)
                    res.set_result_value("source.ip4",result.origin,i)
                    res.set_result_value("destination.ip4",result.destination_address,i)
                    res.set_result_value("ripeatlas.probe_id", result.probe_id, i)
                    res.set_result_value("time", mplane.model.When(a=result.created), i)
                    i += 1
                measstart = result.created if result.created < measstart else measstart
                measend = result.created if result.created > measend else measend
        else:
            raise ValueError("Unknown specification label: " + spec.get_label())
        res.set_when(mplane.model.When(a = measstart, b = measend))
        return res

class AtlasCreateService(mplane.scheduler.Service):
    def __init__(self, capability):
        return super().__init__(capability)
    
    def run(self, spec, check_interrupt):
        probeids = spec.get_parameter_value("ripeatlas.probe_id")
        if not isinstance(probeids, list):
            probeids = [probeids]
        source = cousteau.AtlasSource(type="probes", value=",".join([str(id) for id in probeids]), requested=len(probeids))
        measurement = cousteau.measurement.AtlasMeasurement()
        if  "ripeatlas-ping-create" in spec.get_label():
            measurement = cousteau.Ping(af = 4, target = str(spec.get_parameter_value("destination.ip4")),
                                        description = "test", interval = spec.when().period().seconds);

        start, end = spec.when().datetimes()
        request = cousteau.AtlasCreateRequest(key = _API_key, measurements = [measurement], sources = [source],
                                              start_time = start, stop_time = end);
        (is_success, response) = request.create()
        if not is_success:
            raise RuntimeError("AtlasCreateRequest was not successful: " + str(response))
        
        res = mplane.model.Result(specification=spec)
        res.set_result_value("ripeatlas.msm_id", response["measurements"][0])
        return res