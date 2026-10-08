import time
from django.core.management.base import BaseCommand
from apps.documents.worker import claim_job,process_job

class Command(BaseCommand):
    help="Process document extraction jobs separately from HTTP requests."
    def add_arguments(self,parser):
        parser.add_argument("--once",action="store_true")
        parser.add_argument("--poll-seconds",type=float,default=2)
    def handle(self,*args,**options):
        try:
            while True:
                job=claim_job()
                if job:
                    process_job(job)
                    self.stdout.write("Processed job "+str(job.pk))
                if options["once"]:return
                if not job:time.sleep(min(30,max(0.1,options["poll_seconds"])))
        except KeyboardInterrupt:
            self.stdout.write("Worker stopped.")
