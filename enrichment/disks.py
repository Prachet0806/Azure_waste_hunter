def enrich_disk(disk):
    disk["idle"] = True  # unattached disks are always wasted
    return disk
