import argparse,importlib.util,io,json,pathlib,socket,sys,unittest
sys.dont_write_bytecode=True
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent));import replay_all as r
ROOT=pathlib.Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True);r.manifest_check();sys.dont_write_bytecode=True
 def no_network(*args,**kwargs):raise RuntimeError('Offline archival tests')
 socket.socket=no_network;socket.create_connection=no_network
 b=r.project('original_corrected',a.output);sys.path.insert(0,str(b));suite=unittest.defaultTestLoader.loadTestsFromName('analysis.test_two_type_primary_decisions');p=r.project('parser_feasibility',a.output);m=r.load('archival_parser_tests',p/'tests/test_method.py');suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(m));stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
 report={'status':'PASS' if result.wasSuccessful() else 'FAIL','tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'scope':'Existing original endpoint-decision and locked parser grammar/fallback tests; no new scientific items','model_calls':0,'API_calls':0};r.dump(a.output/'ARCHIVAL_TEST_REPORT.json',report);(a.output/'tests.log').write_text(stream.getvalue(),'utf-8');print(json.dumps(report));return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
