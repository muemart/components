import mplane.model
import mplane.scheduler
import ripe.atlas.cousteau as cousteau
import ripe.atlas.sagan as sagan
from datetime import datetime
import pytz

def services():
    services = []
    services.append(AtlasResultService(result_common_cap(result_ping_cap())))
    return services

def result_ping_cap():
    cap = mplane.model.Capability(verb = mplane.model.VERB_QUERY, label = "ripeatlas-ping-result", when = "past ... now")
    cap.add_result_column("delay.twoway.icmp.us.min")
    cap.add_result_column("delay.twoway.icmp.us.mean")
    cap.add_result_column("delay.twoway.icmp.us.50pct")
    cap.add_result_column("delay.twoway.icmp.us.max")
    cap.add_result_column("delay.twoway.icmp.count")
    return cap

def result_common_cap(cap):
    cap.add_parameter("ripeatlas.msm_id")
    cap.add_result_column("source.ip4")
    cap.add_result_column("destination.ip4")
    cap.add_result_column("ripeatlas.probe_id")
    cap.add_result_column("time")
    return cap

class AtlasResultService(mplane.scheduler.Service):
    def __init__(self, capability):
        return super().__init__(capability)

    def run(self, spec, check_interrupt):
        starttime, endtime = spec.when().datetimes()
        kwargs = {
            "msm_id": spec.get_parameter_value("ripeatlas.msm_id"),
            "start": starttime,
            "end": endtime
        }
        res = mplane.model.Result(specification=spec)
        if  "ripeatlas-ping-result" in spec.get_label():
            is_success, reqanswer = cousteau.AtlasResultsRequest(**kwargs).create();
            if not is_success:
                raise RuntimeError("AtlasResultsRequest was not successful")
            measstart = datetime.now(tz=pytz.UTC)
            measend = datetime.fromtimestamp(0, pytz.UTC)
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
            res.set_when(mplane.model.When(a = measstart, b = measend))
        elif spec.get_label() == "":
            pass
        else:
            raise ValueError("Unknown specification label: " + spec.get_label())
        return res