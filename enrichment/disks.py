def enrich_disk(disk):
    disk["assessment_status"] = "candidate"
    disk["assessment_reason"] = "Disk is unattached; verify retention and recovery requirements before action."
    return disk
