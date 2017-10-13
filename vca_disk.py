
# Copyright header....

DOCUMENTATION = '''
---
module: vca_disk
short_description: This is a sentence describing the module
# ... snip ...
'''

EXAMPLES = '''
- name: Creates a new disk in a VDC and attach it to a vm
  vca_disk:
    vapp_name: tower
    vm_name: myVM
    state=present
    operation: attach
    storage_profile='Silver'
    vdc_name=VDC1
    username=<your username here>
    password=<your password here>
'''

DEFAULT_DISK_OPERATION = 'noop'

DISK_STATES = ['present', 'absent']
DISK_STATUS = ['absent', 'attached', 'detached']

DISK_OPERATIONS = ['attach', 'detach', 'noop']

DISK_OPERATION_TO_STATUS =  {'attach': 'attached', 'detach': 'detached'}

def get_instance(module):
    vdc_name = module.params['vdc_name']
    disk_name = module.params['disk_name']

    inst = dict(disk_name=disk_name, state='absent')
    try:
        the_vdc = module.vca.get_vdc(vdc_name)
        if the_vdc:
            inst['status'] = get_disk_status(module, the_vdc)
        return inst
    except VcaError:
        return inst

def get_disk_status(module, the_vdc):
    disk_name = module.params['disk_name']
    vdc_name = module.params['vdc_name']
    vm_name = module.params['vm_name']
    #disk_refs = filter(lambda disk:
    #                     disk.get_name() == disk_name,
    #                     module.vca.get_diskRefs(the_vdc))
    disk = filter(lambda disk:
                  disk[0].get_name() == disk_name,
                  module.vca.get_disks(vdc_name))

    if len(disk) == 0:
        return 'absent'
    else:
        vm = filter(lambda vm:
                    vm.get_name() == vm_name,
                    disk[0][1])
        if len(vm) == 1:
            return 'attached'
        else:
            return 'detached'

def create(module):
    vdc_name = module.params['vdc_name']
    disk_name = module.params['disk_name']
    disk_size = module.params['disk_size']
    bus_type = module.params['bus_type']
    bus_sub_type = module.params['bus_sub_type']
    disk_description = module.params['disk_description']
    storage_profile = module.params['storage_profile']

    result = module.vca.add_disk(vdc_name, disk_name, int(disk_size)*1024**3, int(bus_type), bus_sub_type, disk_description, storage_profile)

    if result[0]:
        # Waiting for disk creation to complete
        result = module.vca.block_until_completed(result[1].Tasks[0])
    else:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(result[1])
        module.fail("Disk creation failed: " + root.get('message'))


def delete(module):
    vdc_name = module.params['vdc_name']
    disk_name = module.params['disk_name']

    result = module.vca.delete_disk(vdc_name, disk_name)

    if result[0]:
        # Waiting for disk deletion to complete
        result = module.vca.block_until_completed(result[1])
    else:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(result[1])
        module.fail("Disk deletion failed: " + root.get('message'))

def do_operation(module):
    vdc_name = module.params['vdc_name']
    vapp_name = module.params['vapp_name']
    vm_name = module.params['vm_name']
    operation = module.params['operation']
    disk_name = module.params['disk_name']
    bus_number = module.params['bus_number']
    unit_number = module.params['unit_number']


    the_vdc = module.vca.get_vdc(vdc_name)
    if the_vdc:
        the_vapp = module.vca.get_vapp(the_vdc, vapp_name)
    if the_vapp:
        # get disk href
        link = filter(lambda link:
                      link.get_name() == disk_name,
                      module.vca.get_diskRefs(the_vdc))

        if len(link) == 1:
            # get disk object
            disk = filter(lambda disk:
                          disk[0].get_name() == disk_name,
                          module.vca.get_disks(vdc_name))

            vm = filter(lambda vm:
                        vm.get_name() == vm_name,
                        disk[0][1])

            if operation == 'attach':
                if len(vm) == 0:
                    if bus_number and unit_number:
                        task = the_vapp.attach_disk_to_vm(vm_name, link[0], bus_number, unit_number)
                    else:
                        task = the_vapp.attach_disk_to_vm(vm_name, link[0])
                    assert task
                    result = module.vca.block_until_completed(task)
                    if not result:
                        module.fail('Disk attachement failed');
                else:
                    module.fail('Disk already attached');
            elif operation == 'detach':
                the_vapp = module.vca.get_vapp(the_vdc, vapp_name)
                if len(vm) == 1:
                    task = the_vapp.detach_disk_from_vm(vm_name, link[0])
                    assert task
                    result = module.vca.block_until_completed(task)
                    if not result:
                        module.fail('Disk detachement failed');
                else:
                    module.fail('Disk: ' + disk_name + ' not attached to vm: ' + vm_name);
        else:
            module.fail('Disk: ' + disk_name + ' not found');
    else:
        module.fail('vApp: ' + vapp_name + ' not found in vDC: ' + vdc_name);


def main():

    argument_spec = dict(
        vapp_name=dict(required=True),
        vdc_name=dict(required=True),
        disk_name=dict(required=True),
        disk_size=dict(required=True),
        bus_number=dict(),
        unit_number=dict(),
        bus_type=dict(),
        bus_sub_type=dict(),
        disk_description=dict(),
        storage_profile=dict(),
        vm_name=dict(required=True),
        operation=dict(default=DEFAULT_DISK_OPERATION, choices=DISK_OPERATIONS),
        state=dict(default='present', choices=DISK_STATES)
    )

    module = VcaAnsibleModule(argument_spec=argument_spec,
                              supports_check_mode=True)

    state = module.params['state']
    operation = module.params['operation']

    result = dict(changed=False)

    instance = get_instance(module)

    if state == 'absent' and instance.get('status') != 'absent':
        if not module.check_mode:
            if instance.get('status') == 'attached':
                if operation == 'detach':
                    do_operation(module)
                else:
                    module.fail('Disk must be detached before deletion')
            delete(module)
            result['changed'] = True
        else:
            result['changed'] = False

    elif state != 'absent':
        if instance.get('status') == 'absent':
            if not module.check_mode:
                create(module)
                instance['status'] = 'present'
                result['changed'] = True
            else:
                result['changed'] = False

        if DISK_OPERATION_TO_STATUS.get(operation) != instance.get('status') and operation != 'noop':
            if not module.check_mode:
                do_operation(module)
                instance['status'] = DISK_OPERATION_TO_STATUS.get(operation)
                result['changed'] = True
            else:
                result['changed'] = False


    if module.check_mode:
        # Check if any changes would be made but don't actually make those changes
        module.exit_json(changed=False)

    #module.fail(instance['state']);


    vdc_name = module.params['vdc_name']
    vapp_name = module.params['vapp_name']
    vm_name = module.params['vm_name']
    disk_name = module.params['disk_name']

    # retrieve and return disk details
    the_vdc = module.vca.get_vdc(vdc_name)
    the_vapp = module.vca.get_vapp(the_vdc, vapp_name)
    vms = the_vapp.me.Children.Vm
    vm = (
        filter(lambda vm:
               vm.get_name() == vm_name,
               vms)[0])
    sections = vm.get_Section()
    virtualHardwareSection = (
        filter(lambda section:
                section.__class__.__name__ ==
                "VirtualHardwareSection_Type",
                sections)[0])
    items = virtualHardwareSection.get_Item()

    _url = '{http://www.vmware.com/vcloud/v1.5}disk'


    disk_hrefs = filter(lambda disk:
                       disk.get_name() == disk_name,
                       module.vca.get_diskRefs(the_vdc))

    if len(disk_hrefs) >0:
        disk = filter(lambda item: item.get_ResourceType() == 17 and
                   item.HostResource[0].get_anyAttributes_().
                   get(_url) == disk_hrefs[0].href,
                   items)

        if len(disk) == 1:
            scsi_ctrl_id = disk[0].get_Parent().get_valueOf_()
            scsi_ctrl = filter(lambda item: item.get_InstanceID().
                               get_valueOf_() == scsi_ctrl_id,
                               items)

            result['ansible_facts'] = dict(bus_number=scsi_ctrl[0].get_Address().get_valueOf_(), unit_number=disk[0].get_AddressOnParent().get_valueOf_())

        #module.fail(disk[0].get_ResourceType())

    #if disk.HostResource[0].get_anyAttributes_().get(_url) == disk_href:
    #    module.fail("Found")

    #module.fail(disk.HostResource[0].get_anyAttributes_().get("{http://www.vmware.com/vcloud/v1.5}disk"))
    #module.fail(disk.HostResource[0].get_anyAttributes_())
    #module.fail(disk.get_HostResource().count("29f4b6d7-172b-42a4-a05b-a9ee65a44f04"))

    return module.exit(**result)

# import module snippets
from ansible.module_utils.basic import *
from ansible.module_utils.vca import *
if __name__ == '__main__':
    main()
