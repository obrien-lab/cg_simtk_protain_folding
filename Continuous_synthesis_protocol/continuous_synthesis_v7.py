#!/usr/bin/env python3

try:
    from openmm.app import *
    from openmm import *
    from openmm.unit import *
except:
    from simtk.openmm.app import *
    from simtk.openmm import *
    from simtk.unit import *

from sys import stdout, exit, stderr
import getopt, os, time, multiprocessing, random, math, traceback, io
import parmed as pmd
import numpy as np

usage = '\nUsage: python continuous_synthesis.py\n' \
        '       --ctrlfile | -f <CSP.ctrl> Control file for continuous synthesis\n'\
        '       [--help | -h] Print this information\n\n'\
        ' Example of cntrol file:\n'\
        '  use_gpu = 0\n'\
        '  tpn = 20\n'\
        '  ppn = 1\n'\
        '  num_traj = 20\n'\
        '  prot_psf = setup/1cli_chain_a_rebuilt_mini_ca.psf\n'\
        '  prot_top = setup/1cli_chain_a_rebuilt_mini_ca.top\n'\
        '  prot_param = setup/1cli_chain_a_rebuilt_ultimate.prm\n'\
        '  ribo_psf = setup/combine_ribo_L24_v2.psf\n'\
        '  ribo_top = setup/combine_ribo_L24_v2.top\n'\
        '  ribo_param = setup/combine_ribo_L24_v2.prm\n'\
        '  starting_strucs = setup/combine_ribo_L24.cor\n'\
        '  start_nascent_chain_length = 1\n'\
        '  total_nascent_chain_length = 345\n'\
        '  temp_prod = 310\n'\
        '  mrna_seq = setup/1cli_mrna_sequence.txt\n'\
        '  trans_times = setup/fluitt_trans_times_mean_840000.txt\n'\
        '  uniform_ta = 0\n'\
        '  uniform_mfpt = 0\n'\
        '  ribo_free_mask = L24 : 42 - 56\n'\
        '  time_stage_1 = 0.00068\n'\
        '  time_stage_2 = 0.00838\n'\
        '  ribosome_traffic = 1\n'\
        '  initiation_rate = 0.09\n'\
        '  scale_factor = 4331293\n'\
        '  x_eject = 60\n'\
        '  log_file = info.log\n'\
        '  restart = 0\n'

def run_elongation(index, start_nascent_chain_length, total_nascent_chain_length, previous_rnc_cor_file):
    global prot_psf_pmd, ribo_psf_pmd, ribo_resid_list, codon_list, use_gpu, dev_index_list
    global ppn, temp_prod, timestep, fbsolu, forcefield, constraint_tolerance, nsteps_save, scale_factor
    global nonbond_cutoff, switch_cutoff
    global time_stage_1, time_stage_2, real_mean_fpt_list, intrinsic_mean_fpt_list, ribosome_traffic

    traj_dir = 'traj/'+str(index)
    out_file = '../../output/'+str(index)+'.out'
    if not os.path.exists(traj_dir):
        os.mkdir(traj_dir)
    os.chdir(traj_dir)
    
    if use_gpu == 0:
        properties = {'Threads': str(ppn)}
        platform = Platform.getPlatformByName('CPU')
    else:
        #dev_index = dev_index_list[int(multiprocessing.current_process().name.split('-')[-1])-1]
        dev_index = int(multiprocessing.current_process().name.split('-')[-1])-1
        properties = {'CudaPrecision': 'mixed'}
        properties["DeviceIndex"] = "%d"%(dev_index);
        platform = Platform.getPlatformByName('CUDA')

    for nascent_chain_length in range(start_nascent_chain_length, total_nascent_chain_length+1):
        rand = random.randint(10,1000000000)
        # Read the codon insertion time of the next codon
        sampled_time_stage_1 = sample_fpt_dist(time_stage_1)
        simulation_time_stage_1 = sampled_time_stage_1*1e9/scale_factor
        step_stage_1 = int(simulation_time_stage_1 / timestep.value_in_unit(nanoseconds))

        if real_mean_fpt_list[nascent_chain_length-1]-intrinsic_mean_fpt_list[nascent_chain_length-1] > 0:
            sampled_time_stage_2 = sample_fpt_dist(time_stage_2+real_mean_fpt_list[nascent_chain_length-1]
                -intrinsic_mean_fpt_list[nascent_chain_length-1])
        else: # In case that real time is shorter than intrinsic time due to the sampling problem when calculating ribosome traffic
            sampled_time_stage_2 = sample_fpt_dist(time_stage_2)
        simulation_time_stage_2 = sampled_time_stage_2*1e9/scale_factor
        step_stage_2 = int(simulation_time_stage_2 / timestep.value_in_unit(nanoseconds))

        sampled_time_stage_3 = sample_fpt_dist(intrinsic_mean_fpt_list[nascent_chain_length]-time_stage_1-time_stage_2)
        simulation_time_stage_3 = sampled_time_stage_3*1e9/scale_factor
        step_stage_3 = int(simulation_time_stage_3 / timestep.value_in_unit(nanoseconds))

        fo = open(out_file, 'a')
        fo.write('#'*92 + '\n')
        fo.write('--> Elongation at length %d with random seed %d\n'%(nascent_chain_length, rand))
        #if uniform_ta == 1:
        #    fo.write('    Mean in vivo AA insertion time: %f s\n'%(intrinsic_mean_fpt_list[nascent_chain_length]))
        #else:
        #    if ribosome_traffic == 1:
        #        fo.write('    Mean in vivo intrinsic AA insertion time for next codon %s: %f s\n'%(codon_list[nascent_chain_length], 
        #            intrinsic_mean_fpt_list[nascent_chain_length]))
        #        fo.write('    Mean in vivo real AA insertion time for next codon %s: %f s\n'%(codon_list[nascent_chain_length], 
        #            real_mean_fpt_list[nascent_chain_length]))
        #    else:
        #        fo.write('    Mean in vivo AA insertion time for next codon %s: %f s\n'%(codon_list[nascent_chain_length], 
        #            intrinsic_mean_fpt_list[nascent_chain_length]))
        #fo.write('    Mean in silico AA insertion time: %f ns\n'%(real_mean_fpt_list[nascent_chain_length]*1e9/scale_factor))
        fo.write('    Mean in vivo peptidyl transfer dwell time: %f s\n'%time_stage_1)
        fo.write('    Mean in silico peptidyl transfer dwell time: %f ns\n'%(time_stage_1*1e9/scale_factor))
        fo.write('    Sampled in silico peptidyl transfer dwell time: %f ns\n'%simulation_time_stage_1)
        fo.write('    Simulation steps for in silico dwell time before peptidyl transfer: %d\n'%(step_stage_1))

        fo.write('    Mean in vivo translocation dwell time: %f s\n'%(time_stage_2+real_mean_fpt_list[nascent_chain_length-1]
            -intrinsic_mean_fpt_list[nascent_chain_length-1]))
        fo.write('    Mean in silico translocation dwell time: %f ns\n'%((time_stage_2+real_mean_fpt_list[nascent_chain_length-1]
            -intrinsic_mean_fpt_list[nascent_chain_length-1])*1e9/scale_factor))
        fo.write('    Sampled in silico translocation dwell time: %f ns\n'%simulation_time_stage_2)
        fo.write('    Simulation steps for in silico dwell time before translocation: %d\n'%(step_stage_2))

        fo.write('    Mean in vivo tRNA binding dwell time: %f s\n'%(intrinsic_mean_fpt_list[nascent_chain_length]-time_stage_1
            -time_stage_2))
        fo.write('    Mean in silico tRNA binding dwell time: %f ns\n'%((intrinsic_mean_fpt_list[nascent_chain_length]-time_stage_1
            -time_stage_2)*1e9/scale_factor))
        fo.write('    Sampled in silico tRNA binding dwell time: %f ns\n'%simulation_time_stage_3)
        fo.write('    Simulation steps for in silico dwell time before next tRNA binding: %d\n'%(step_stage_3))

        #fo.write('    Total sampled in silico AA insertion time: %f ns\n'%(simulation_time_stage_1+simulation_time_stage_2
        #    +simulation_time_stage_3))
        fo.close()

        try:
            previous_rnc_cor_file = elongation(nascent_chain_length, prot_psf_pmd, ribo_psf_pmd, previous_rnc_cor_file, 
                [step_stage_1, step_stage_2, step_stage_3], rand, out_file, properties, platform)
        except Exception as e:
            traceback.print_exc()
            previous_rnc_cor_file = False
            
        if previous_rnc_cor_file == False:
            break
        elif nascent_chain_length < len(prot_psf_pmd.residues):
            fo = open(out_file, 'a')
            fo.write('--> Elongation finished at length %d\n'%nascent_chain_length)
            fo.close()
        else:
            fo = open(out_file, 'a')
            fo.write('#'*92 + '\n')
            fo.write('--> All Done\n')
            fo.close()
    os.chdir('../../')


def elongation(nascent_chain_length, prot_psf, ribo_psf, previous_rnc_cor_file, simulation_steps, rand, out_file, properties, platform):
    global ppn, temp_prod, timestep, fbsolu, forcefield, constraint_tolerance, nsteps_save, ribo_resid_list
    global use_gpu, ribo_free_mask, spherical_restraint_mask, spherical_restraint_center, spherical_restraint_radius

    rnc_psf_pmd = prot_psf[':1-'+str(nascent_chain_length)] + ribo_psf # combine ribosome psf with nascent chain psf
    
    rnc_psf_pmd.save('rnc_l'+str(nascent_chain_length)+'.psf', overwrite=True)
    rnc_psf = CharmmPsfFile('rnc_l'+str(nascent_chain_length)+'.psf')
    
    top = rnc_psf.topology
    # re-name residues that are changed by openmm
    for resid, res in enumerate(top.residues()):
        if res.name != rnc_psf_pmd.residues[resid].name:
            res.name = rnc_psf_pmd.residues[resid].name
    # re-name segid that are changed by openmm
    for resid, res in enumerate(top.residues()):
        if res.chain.id != rnc_psf_pmd.residues[resid].segid:
            res.chain.id = rnc_psf_pmd.residues[resid].segid
    
    # renumber ribosome resid
    idx = 0
    for res in rnc_psf_pmd.residues:
        if res.segid != 'A':
            res.number = ribo_resid_list[idx]
            idx += 1
    rnc_psf_pmd.save('rnc_l'+str(nascent_chain_length)+'.psf', overwrite=True)
    formate_psf_vmd('rnc_l'+str(nascent_chain_length)+'.psf')

    if ribo_free_mask == '':
        ribo_free_idx = []
    else:
        try:
            ribo_free_idx = parse_mask(rnc_psf_pmd, ribo_free_mask)
        except Exception as e:
            traceback.print_exc()
            return False
    if ribo_free_idx == False:
        return False
        
    if spherical_restraint_mask == '':
        sp_rst_idx = []
    else:
        try:
            sp_rst_idx = parse_mask(rnc_psf_pmd, spherical_restraint_mask)
        except Exception as e:
            traceback.print_exc()
            return False
    if sp_rst_idx == False:
        return False
    
    fo = open(out_file, 'a')
    if ribo_free_idx == []:
        fo.write('    Free atom index: None\n')
    else:
        n_col = 10
        n_row = math.ceil(len(ribo_free_idx) / n_col)
        fo.write('    Free atom index:\n')
        for i in range(n_row):
            fo.write(' '*20)
            for j in range(i*n_col, min((i+1)*n_col, len(ribo_free_idx))):
                fo.write('%5d '%ribo_free_idx[j])
            fo.write('\n')
    
    if sp_rst_idx == []:
        fo.write('    Spherical restraint: None\n')
    else:
        fo.write('    Spherical restraint: Center %s; Radius %.4f\n'%(str(spherical_restraint_center), spherical_restraint_radius))
    fo.close()

    previous_rnc_cor = CharmmCrdFile(previous_rnc_cor_file)
    current_rnc_cor = previous_rnc_cor.positions
    # add new amino acid bead to RNC

    # build residue template map
    template_map = {}
    for chain in top.chains():
        for res in chain.residues():
            template_map[res] = res.name

    seeded_random = random.Random(rand)

    rand = seeded_random.randint(10,1000000000)
    current_rnc_cor = A_site_tRNA_binding(top, current_rnc_cor, nascent_chain_length, rnc_psf_pmd, 
        out_file, template_map, platform, properties, rand, simulation_steps[0], ribo_free_idx, sp_rst_idx)
    if current_rnc_cor == False:
        return False

    rand = seeded_random.randint(10,1000000000)
    current_rnc_cor = peptide_bond_formation(top, current_rnc_cor, nascent_chain_length, rnc_psf_pmd, 
        out_file, template_map, platform, properties, rand, simulation_steps[1], ribo_free_idx, sp_rst_idx)
    if current_rnc_cor == False:
        return False

    rand = seeded_random.randint(10,1000000000)
    current_rnc_cor = translocation_AtR(top, current_rnc_cor, nascent_chain_length, rnc_psf_pmd, 
        out_file, template_map, platform, properties, rand, simulation_steps[2], ribo_free_idx, sp_rst_idx)
    if current_rnc_cor == False:
        return False
    else:
        return 'rnc_l'+str(nascent_chain_length)+'_stage_3_final.cor'

# A-site tRNA binding
def A_site_tRNA_binding(top, current_rnc_cor, nascent_chain_length, rnc_psf_pmd, 
    out_file, template_map, platform, properties, rand, simulation_steps, ribo_free_idx, sp_rst_idx):
    global temp_prod, fbsolu, timestep, constraint_tolerance, forcefield

    # A-site resid 76 (last residue) ribose R 
    AtR_id76_R_index = 0
    for res in top.residues():
        if res.chain.id == 'AtR':
            AtR_id76_res = res
    for atom in AtR_id76_res.atoms():
        if atom.name == 'R':
            AtR_id76_R_index = atom.index
    AtR_id76_R_coor = np.array(list(current_rnc_cor[AtR_id76_R_index-1].value_in_unit(angstroms)), 
        dtype=np.float64)
    alpha = 10*degree
    new_AA_coor = AtR_id76_R_coor + np.array([math.cos(alpha.value_in_unit(radian)), 
        math.sin(alpha.value_in_unit(radian)), 0], dtype=np.float64) * 4.27
    new_AA_coor = tuple(new_AA_coor)
    current_rnc_cor.insert(nascent_chain_length-1, Quantity(new_AA_coor, angstroms))
    rnc_psf_pmd.positions = current_rnc_cor
    #rnc_psf_pmd.write_pdb('rnc_l'+str(nascent_chain_length)+'_0.pdb', charmm=True)
    current_rnc_cor = rnc_psf_pmd.positions # most important

    fo = open(out_file, 'a')
    fo.write('--> Create system for A-site tRNA binding\n')
    system = create_elongation_system(forcefield, rnc_psf_pmd, top, template_map, 1, nascent_chain_length, ribo_free_idx, sp_rst_idx)
    fo.write('    Done\n')
    fo.close()

    # fix everything other than the C-terminal 15 residues of the nascent chain
    for atom in top.atoms():
        if not (atom.residue.chain.id == 'A' and int(atom.id) > nascent_chain_length - 15):
            system.setParticleMass(atom.index, 0*dalton)
    rm_cons_0_mass(system)
    # END fix everything other than the C-terminal 15 residues of the nascent chain
    
    forcegroups = forcegroupify(system)
    # minimize steric clashes of the newly inserted residue
    integrator = LangevinIntegrator(temp_prod, fbsolu, timestep)
    integrator.setRandomNumberSeed(rand)
    # Attempt of creating the simulation object (sometimes fail due to CUDA environment)
    i_attempt = 0
    while True:
        try:
            simulation = Simulation(top, system, integrator, platform, properties)
        except Exception as e:
            print('Error occurred at attempt %d...'%(i_attempt+1))
            traceback.print_exc()
            i_attempt += 1
            continue
        else:
            break
    simulation.context.setPositions(current_rnc_cor)

    energy = simulation.context.getState(getEnergy=True).getPotentialEnergy().value_in_unit(kilocalorie/mole)
    fo = open(out_file, 'a')
    fo.write('    Potential energy before minimization: %.4f kcal/mol\n'%(energy))
    fo.close()
    #getEnergyDecomposition(fo, simulation.context, forcegroups)
    try:
        simulation.minimizeEnergy(tolerance=1*kilojoule/mole)
    except Exception as e:
        fo = open(out_file, 'a')
        fo.write("Error: crashed at min1\n")
        fo.write(str(e)+'\n')
        getEnergyDecomposition(fo, simulation.context, forcegroups)
        current_rnc_cor = simulation.context.getState(getPositions=True).getPositions()
        rnc_psf_pmd.positions = current_rnc_cor
        rnc_psf_pmd.save('rnc_l'+str(nascent_chain_length)+'_crashed_min1.cor', format='charmmcrd', overwrite=True)
        fo.close()
        return False
    energy = simulation.context.getState(getEnergy=True).getPotentialEnergy().value_in_unit(kilocalorie/mole)
    fo = open(out_file, 'a')
    fo.write('    Potential energy after minimization: %.4f kcal/mol\n'%(energy))
    getEnergyDecomposition(fo, simulation.context, forcegroups)
    fo.close()
    current_rnc_cor = simulation.context.getState(getPositions=True).getPositions()
    rnc_psf_pmd.positions = current_rnc_cor
    rnc_psf_pmd.write_pdb('rnc_l'+str(nascent_chain_length)+'_min_1.pdb', charmm=True)

    system = create_elongation_system(forcefield, rnc_psf_pmd, top, template_map, 1, nascent_chain_length, ribo_free_idx, sp_rst_idx)
    (current_rnc_cor, current_rnc_velocities) = equilibration(top, current_rnc_cor, nascent_chain_length, rnc_psf_pmd, 
        out_file, system, 1, platform, properties, rand, simulation_steps, [], ribo_free_idx)
    return current_rnc_cor

# peptide bond formation
def peptide_bond_formation(top, current_rnc_cor, nascent_chain_length, rnc_psf_pmd, 
    out_file, template_map, platform, properties, rand, simulation_steps, ribo_free_idx, sp_rst_idx):
    global temp_prod, fbsolu, timestep, constraint_tolerance, forcefield
    global nonbond_cutoff, switch_cutoff
    
    fo = open(out_file, 'a')
    fo.write('--> Create system for peptide bond formation\n')
    system = create_elongation_system(forcefield, rnc_psf_pmd, top, template_map, 2, nascent_chain_length, ribo_free_idx, sp_rst_idx)
    fo.write('    Done\n')
    fo.close()

    # fix everything other than the C-terminal 15 residues of the nascent chain
    for atom in top.atoms():
        if not (atom.residue.chain.id == 'A' and int(atom.id) > nascent_chain_length - 15):
            system.setParticleMass(atom.index, 0*dalton)
    rm_cons_0_mass(system)
    # END fix everything other than the C-terminal 15 residues of the nascent chain

    # minimize steric clashes of the newly inserted residue
    integrator = LangevinIntegrator(temp_prod, fbsolu, timestep)
    integrator.setRandomNumberSeed(rand)
    forcegroups = forcegroupify(system)
    while True:
        try:
            simulation = Simulation(top, system, integrator, platform, properties)
        except Exception as e:
            print('Error occurred at attempt %d...'%(i_attempt+1))
            traceback.print_exc()
            i_attempt += 1
            continue
        else:
            break
    simulation.context.setPositions(current_rnc_cor)

    energy = simulation.context.getState(getEnergy=True).getPotentialEnergy().value_in_unit(kilocalorie/mole)
    fo = open(out_file, 'a')
    fo.write('    Potential energy before minimization: %.4f kcal/mol\n'%(energy))
    fo.close()
    #getEnergyDecomposition(fo, simulation.context, forcegroups)
    try:
        simulation.minimizeEnergy(tolerance=1*kilojoule/mole)
    except Exception as e:
        fo = open(out_file, 'a')
        fo.write("Error: crashed at min2\n")
        fo.write(str(e)+'\n')
        getEnergyDecomposition(fo, simulation.context, forcegroups)
        current_rnc_cor = simulation.context.getState(getPositions=True).getPositions()
        rnc_psf_pmd.positions = current_rnc_cor
        rnc_psf_pmd.save('rnc_l'+str(nascent_chain_length)+'_crashed_min2.cor', format='charmmcrd', overwrite=True)
        fo.close()
        return False
    energy = simulation.context.getState(getEnergy=True).getPotentialEnergy().value_in_unit(kilocalorie/mole)
    fo = open(out_file, 'a')
    fo.write('    Potential energy after minimization: %.4f kcal/mol\n'%(energy))
    getEnergyDecomposition(fo, simulation.context, forcegroups)
    fo.close()
    current_rnc_cor = simulation.context.getState(getPositions=True).getPositions()
    rnc_psf_pmd.positions = current_rnc_cor
    rnc_psf_pmd.write_pdb('rnc_l'+str(nascent_chain_length)+'_min_2.pdb', charmm=True)

    system = create_elongation_system(forcefield, rnc_psf_pmd, top, template_map, 2, nascent_chain_length, ribo_free_idx, sp_rst_idx)
    (current_rnc_cor, current_rnc_velocities) = equilibration(top, current_rnc_cor, nascent_chain_length, rnc_psf_pmd, 
        out_file, system, 2, platform, properties, rand, simulation_steps, [], ribo_free_idx)
    return current_rnc_cor

# translocation of A-site tRNA to P-site
def translocation_AtR(top, current_rnc_cor, nascent_chain_length, rnc_psf_pmd, 
    out_file, template_map, platform, properties, rand, simulation_steps, ribo_free_idx, sp_rst_idx):
    global temp_prod, fbsolu, timestep, constraint_tolerance, forcefield
    global nonbond_cutoff, switch_cutoff, prot_psf_pmd
    
    fo = open(out_file, 'a')
    fo.write('--> Create system for A-site tRNA translocation\n')
    system = create_elongation_system(forcefield, rnc_psf_pmd, top, template_map, 3, nascent_chain_length, ribo_free_idx, sp_rst_idx)
    fo.write('    Done\n')
    fo.close()

    # fix everything other than the C-terminal 15 residues of the nascent chain
    for atom in top.atoms():
        if not (atom.residue.chain.id == 'A' and int(atom.id) > nascent_chain_length - 15):
            system.setParticleMass(atom.index, 0*dalton)
    rm_cons_0_mass(system)
    # END fix everything other than the C-terminal 15 residues of the nascent chain

    # minimize steric clashes of the newly inserted residue
    integrator = LangevinIntegrator(temp_prod, fbsolu, timestep)
    integrator.setRandomNumberSeed(rand)
    forcegroups = forcegroupify(system)
    while True:
        try:
            simulation = Simulation(top, system, integrator, platform, properties)
        except Exception as e:
            print('Error occurred at attempt %d...'%(i_attempt+1))
            traceback.print_exc()
            i_attempt += 1
            continue
        else:
            break
    simulation.context.setPositions(current_rnc_cor)

    energy = simulation.context.getState(getEnergy=True).getPotentialEnergy().value_in_unit(kilocalorie/mole)
    fo = open(out_file, 'a')
    fo.write('    Potential energy before minimization: %.4f kcal/mol\n'%(energy))
    fo.close()
    #getEnergyDecomposition(fo, simulation.context, forcegroups)
    try:
        simulation.minimizeEnergy(tolerance=1*kilojoule/mole)
    except Exception as e:
        fo = open(out_file, 'a')
        fo.write("Error: crashed at min3\n")
        fo.write(str(e)+'\n')
        getEnergyDecomposition(fo, simulation.context, forcegroups)
        current_rnc_cor = simulation.context.getState(getPositions=True).getPositions()
        rnc_psf_pmd.positions = current_rnc_cor
        rnc_psf_pmd.save('rnc_l'+str(nascent_chain_length)+'_crashed_min3.cor', format='charmmcrd', overwrite=True)
        fo.close()
        return False
    energy = simulation.context.getState(getEnergy=True).getPotentialEnergy().value_in_unit(kilocalorie/mole)
    fo = open(out_file, 'a')
    fo.write('    Potential energy after minimization: %.4f kcal/mol\n'%(energy))
    getEnergyDecomposition(fo, simulation.context, forcegroups)
    fo.close()
    current_rnc_cor = simulation.context.getState(getPositions=True).getPositions()
    rnc_psf_pmd.positions = current_rnc_cor
    rnc_psf_pmd.write_pdb('rnc_l'+str(nascent_chain_length)+'_min_3.pdb', charmm=True)

    system = create_elongation_system(forcefield, rnc_psf_pmd, top, template_map, 3, nascent_chain_length, ribo_free_idx, sp_rst_idx)
    (current_rnc_cor, current_rnc_velocities) = equilibration(top, current_rnc_cor, nascent_chain_length, rnc_psf_pmd, 
        out_file, system, 3, platform, properties, rand, simulation_steps, [], ribo_free_idx)

    if nascent_chain_length == len(prot_psf_pmd.residues) and current_rnc_cor != False:
        fo = open(out_file, 'a')
        fo.write('--> Elongation finished at length %d\n'%nascent_chain_length)
        fo.write('#'*92 + '\n')
        fo.write('--> Elongation termination at length %d\n'%nascent_chain_length)
        seeded_random = random.Random(rand)
        rand = seeded_random.randint(10,1000000000)
        fo.write('--> Nascent chain ejection with random seed %d\n'%(rand))
        fo.close()
        system = create_elongation_system(forcefield, rnc_psf_pmd, top, template_map, 4, nascent_chain_length, ribo_free_idx, sp_rst_idx)
        (current_rnc_cor, current_rnc_velocities) = equilibration(top, current_rnc_cor, nascent_chain_length, rnc_psf_pmd, 
            out_file, system, 4, platform, properties, rand, simulation_steps, current_rnc_velocities, ribo_free_idx)
        rand = seeded_random.randint(10,1000000000)
        fo = open(out_file, 'a')
        fo.write('--> Nascent chain dissociation with random seed %d\n'%(rand))
        fo.close()
        system = create_elongation_system(forcefield, rnc_psf_pmd, top, template_map, 5, nascent_chain_length, ribo_free_idx, sp_rst_idx)
        (current_rnc_cor, current_rnc_velocities) = equilibration(top, current_rnc_cor, nascent_chain_length, rnc_psf_pmd, 
            out_file, system, 5, platform, properties, rand, simulation_steps, current_rnc_velocities, ribo_free_idx)

    return current_rnc_cor

# equilibration
def equilibration(top, current_rnc_cor, nascent_chain_length, rnc_psf_pmd, out_file, system, 
    stage, platform, properties, rand, simulation_steps, current_rnc_velocities, ribo_free_idx):
    global temp_prod, fbsolu, timestep, constraint_tolerance, forcefield, nsteps_save
    global restraint_coor, prot_psf_pmd, x_eject, use_gpu

    if_flex_PTC = 0

    if if_flex_PTC == 1:
        k = 10*kilocalories_per_mole/angstroms**2
        rest_idx = 0
        for atom in top.atoms():
            coor = current_rnc_cor[atom.index].value_in_unit(angstroms)
            d = ((coor[0]-12)**2 + coor[1]**2 + coor[2]**2)**0.5
            #d = (coor[1]**2 + coor[2]**2)**0.5
            if atom.residue.chain.id != 'A' and atom.residue.chain.id != 'AtR' and atom.residue.chain.id != 'PtR' and d <= 12: 
            # select interaction sites around the peptidyl transferase center
                system.getForce(system.getNumForces()-1).addParticle(atom.index, (k.value_in_unit(kilojoules_per_mole/nanometers**2),
                    restraint_coor[rest_idx][0]/10, restraint_coor[rest_idx][1]/10, restraint_coor[rest_idx][2]/10))
                rest_idx += 1

        for atom in top.atoms():
            coor = current_rnc_cor[atom.index].value_in_unit(angstroms)
            d = ((coor[0]-12)**2 + coor[1]**2 + coor[2]**2)**0.5
            #d = (coor[1]**2 + coor[2]**2)**0.5
            if atom.residue.chain.id != 'A' and (not atom.index in ribo_free_idx) and (atom.residue.chain.id == 'AtR' or 
                atom.residue.chain.id == 'PtR' or d > 12): 
            # select all interaction sites not in the partial sphere around the PTC
                system.setParticleMass(atom.index, 0*dalton)
    else:
        for atom in top.atoms():
            if atom.residue.chain.id != 'A' and (not atom.index in ribo_free_idx): 
            # select all interaction sites not in the partial sphere around the PTC
                system.setParticleMass(atom.index, 0*dalton)

    rm_cons_0_mass(system)

    integrator = LangevinIntegrator(temp_prod, fbsolu, timestep)
    integrator.setConstraintTolerance(constraint_tolerance)
    integrator.setRandomNumberSeed(rand)
    forcegroups = forcegroupify(system)
    while True:
        try:
            simulation = Simulation(top, system, integrator, platform, properties)
        except Exception as e:
            print('Error occurred at attempt %d...'%(i_attempt+1))
            traceback.print_exc()
            i_attempt += 1
            continue
        else:
            break
    simulation.context.setPositions(current_rnc_cor)
    if stage == 4 or stage == 5:
        simulation.context.setVelocities(current_rnc_velocities)
    else:
        simulation.context.setVelocitiesToTemperature(temp_prod)
    fo = open(out_file, 'a')
    if use_gpu == 0:
        fo.write('    Running MD on %d CPUs with random seed %d\n'%(int(properties['Threads']), rand))
    else:
        fo.write('    Running MD on GPUs with random seed %d\n'%(rand))
    fo.close()
    simulation.reporters = []
    if stage == 4:
        simulation.reporters.append(DCDReporter('rnc_l'+str(nascent_chain_length)+'_ejection.dcd', nsteps_save))
    elif stage == 5:
        simulation.reporters.append(DCDReporter('rnc_l'+str(nascent_chain_length)+'_dissociation.dcd', nsteps_save))
    else:
        simulation.reporters.append(DCDReporter('rnc_l'+str(nascent_chain_length)+'_stage_'+str(stage)+'.dcd', nsteps_save))

    # Compute the number of degrees of freedom.
    dof = 0
    for i in range(system.getNumParticles()):
        if system.getParticleMass(i) > 0*dalton:
            dof += 3
    dof -= system.getNumConstraints()
    if any(type(system.getForce(i)) == CMMotionRemover for i in range(system.getNumForces())):
        dof -= 3

    start_time = time.time()
    step = 0
    tag_eject = 0
    tag_seperate = 0

    while True:
        step += 1
        try:
            simulation.step(1)
            # Reset spherical restaint center for dissociation
            if stage == 5 and spherical_restraint_mask != '':
                NC_COM = calc_NC_COM(top, simulation.context.getState(getPositions=True).getPositions(), system)
                simulation.context.setParameter('x0', NC_COM[0]*angstrom)
                simulation.context.setParameter('y0', NC_COM[1]*angstrom)
                simulation.context.setParameter('z0', NC_COM[2]*angstrom)
            # Prepare outputs
            if step%nsteps_save == 0:
                progress = step/simulation_steps*100
                Ep = simulation.context.getState(getEnergy=True).getPotentialEnergy().value_in_unit(kilocalorie/mole)
                Ek = simulation.context.getState(getEnergy=True).getKineticEnergy().value_in_unit(kilocalorie/mole)
                Temp = (2*simulation.context.getState(getEnergy=True).getKineticEnergy()/
                    (dof*MOLAR_GAS_CONSTANT_R)).value_in_unit(kelvin)
                end_time = time.time()
                speed = step / (end_time - start_time) * timestep.value_in_unit(nanoseconds) * 3600 * 24
                left_time = convert_time((simulation_steps - step) / step * (end_time - start_time))
                fo = open(out_file, 'a')
                if stage == 4 or stage == 5:
                    current_rnc_cor = simulation.context.getState(getPositions=True).getPositions()
                    (min_d_rn, min_d_n) = calc_min_distance(top, current_rnc_cor)
                    if step/nsteps_save == 1:
                        fo.write('    %11s %15s %15s %7s %10s %11s\n'%('Step', 'Ep(kcal/mol)', 'Ek(kcal/mol)',
                            'Temp(K)', 'd_min(A)', 'Speed(ns/d)'))
                    if stage == 4:
                        fo.write('    %11d %15.4f %15.4f %7.1f %10.3f %11.1f\n'%(step, Ep, Ek, Temp, min_d_n, speed))
                        if min_d_n >= x_eject:
                            tag_eject = 1
                    else:
                        fo.write('    %11d %15.4f %15.4f %7.1f %10.3f %11.1f\n'%(step, Ep, Ek, Temp, min_d_rn, speed))
                        if min_d_rn >= 20:
                            tag_seperate += 1
                        else:
                            tag_seperate = 0
                else:
                    if step/nsteps_save == 1:
                        fo.write('    %6s %11s %15s %15s %7s %11s %11s\n'%('Progress', 'Step', 'Ep(kcal/mol)', 'Ek(kcal/mol)',
                            'Temp(K)', 'Speed(ns/d)', 'Time_remain'))
                    fo.write('    %7.1f%% %11d %15.4f %15.4f %7.1f %11.1f %11s\n'%(progress, step, Ep, Ek, Temp,
                        speed, left_time))
                fo.close()
        except Exception as e:
            fo = open(out_file, 'a')
            simulation.saveState('rnc_l'+str(nascent_chain_length)+'_crashed_step_'+str(step)+
                '_stage_'+str(stage)+'.xml')
            fo.write("Error: crashed at step %d:\n"%(step))
            fo.write(str(e)+'\n')
            getEnergyDecomposition(fo, simulation.context, forcegroups)
            getMaxForce(fo, simulation.context, system)
            ke = simulation.context.getState(getEnergy=True).getKineticEnergy()
            fo.write("    Kinetic energy is %.4f kcal/mol\n"%(ke.value_in_unit(kilocalories_per_mole)))
            fo.close()
            current_rnc_cor = simulation.context.getState(getPositions=True).getPositions()
            rnc_psf_pmd.positions = current_rnc_cor
            rnc_psf_pmd.save('rnc_l'+str(nascent_chain_length)+'_crashed_step_'+str(step)+
                '_stage_'+str(stage)+'.cor', format='charmmcrd', overwrite=True)
            return (False, False)
        
        if stage == 4:
            if tag_eject == 1:
                break
        elif stage == 5:
            if tag_seperate >= 10:
                break
        elif step >= simulation_steps:
            break

    current_rnc_cor = simulation.context.getState(getPositions=True).getPositions()
    current_rnc_velocities = simulation.context.getState(getVelocities=True).getVelocities()
    rnc_psf_pmd.positions = current_rnc_cor
    rnc_psf_pmd.velocities = current_rnc_velocities
    if stage == 4:
        rnc_psf_pmd.save('rnc_l'+str(nascent_chain_length)+'_ejection_final.cor', 
            format='charmmcrd', overwrite=True)
    elif stage == 5:
        rnc_psf_pmd.save('rnc_l'+str(nascent_chain_length)+'_dissociation_final.cor', 
            format='charmmcrd', overwrite=True)
        nc_lig_idx = []
        for atom in top.atoms():
            if atom.residue.chain.id == 'A' or atom.residue.chain.id == 'LIG':
                nc_lig_idx.append(atom.index)
        rnc_psf_pmd[nc_lig_idx].save('prot_l'+str(nascent_chain_length)+'.psf', overwrite=True)
        formate_psf_vmd('prot_l'+str(nascent_chain_length)+'.psf')
        # rnc_psf_pmd[nc_lig_idx].save('prot_l'+str(nascent_chain_length)+'_dissociation_final.cor', 
            # format='charmmcrd', overwrite=True)
        rnc_psf_pmd[nc_lig_idx].save('prot_l'+str(nascent_chain_length)+'_dissociation_final.ncrst', overwrite=True)
        # prot_vel = current_rnc_velocities[nc_lig_idx]
        # fv = open('prot_l'+str(nascent_chain_length)+'_dissociation_final.vel', 'w')
        # for vel in prot_vel:
            # vel = vel.value_in_unit(angstroms/picoseconds)
            # for v in vel:
                # fv.write('%12.6f '%v)
            # fv.write('\n')
        # fv.close()
    else:
        rnc_psf_pmd.save('rnc_l'+str(nascent_chain_length)+'_stage_'+str(stage)+'_final.cor', 
            format='charmmcrd', overwrite=True)
    fo = open(out_file, 'a')
    fo.write('    Done at step %d\n'%step)
    fo.close()
    return (current_rnc_cor, current_rnc_velocities)

# create system for elongation
def create_elongation_system(forcefield, rnc_psf_pmd, top, template_map, stage, nascent_chain_length, ribo_free_idx, sp_rst_idx):
    global nonbond_cutoff, switch_cutoff, x_eject, spherical_restraint_center, spherical_restraint_radius
    try:
        system = forcefield.createSystem(top, nonbondedMethod=CutoffNonPeriodic,
            nonbondedCutoff=nonbond_cutoff, constraints=AllBonds, removeCMMotion=False, 
            ignoreExternalBonds=True, residueTemplates=template_map)
    except Exception as e:
        traceback.print_exc()
    # must set to use switching function explicitly for CG Custom Nonbond Force #
    for force in system.getForces():
        if force.getName() == 'CustomNonbondedForce':
            custom_nb_force = force
            break
    custom_nb_force.setUseSwitchingFunction(True)
    custom_nb_force.setSwitchingDistance(switch_cutoff)
    # End set to use switching function explicitly for CG Custom Nonbond Force #

    ribo_fix_atom_index = []
    nc_atom_index = []
    AtR_atom_index = []
    for atom in top.atoms():
        if (not atom.index in ribo_free_idx) and atom.residue.chain.id != 'A' and atom.residue.chain.id != 'AtR':
            ribo_fix_atom_index.append(atom.index)
        elif atom.residue.chain.id == 'A':
            nc_atom_index.append(atom.index)
        elif atom.residue.chain.id == 'AtR':
            AtR_atom_index.append(atom.index)
    
    # hard copy of the custom nb force for 12-6 inter-molecular force
    custom_nb_force_copy = custom_nb_force.__copy__()
    # Add LJ 12-6 interactions between spherical restrained atoms and nascent chain atoms
    custom_nb_force_copy.setEnergyFunction('ke*charge1*charge2/ep/r*exp(-r/ld)+kv*(a/13/r^12 - c/2/r^6); '+
                                           'ke=ke1*ke2; ep=ep1*ep2; ld=ld1*ld2; kv=kv1*kv2; '+
                                           'a=acoef(index1, index2); c=ccoef(index1, index2)')
    custom_nb_force_copy.setNonbondedMethod(0) # No cutoff
    custom_nb_force_copy.setUseSwitchingFunction(False) # No switch
    custom_nb_force_copy.addInteractionGroup(nc_atom_index, sp_rst_idx)
    system.addForce(custom_nb_force_copy)
    
    # turn off interactions among fixed ribosome atoms and 
    # 12-10-6 interactions between spherical restrained atoms and nascent chain atoms
    custom_nb_force.addInteractionGroup(ribo_fix_atom_index, ribo_free_idx+nc_atom_index)
    for i in range(len(ribo_free_idx)-1):
        custom_nb_force.addInteractionGroup([ribo_free_idx[i]], ribo_free_idx[i+1:])
    for i in range(len(nc_atom_index)-1):
        custom_nb_force.addInteractionGroup([nc_atom_index[i]], nc_atom_index[i+1:])
    ribo_free_exclude_sp_rst_index = [i for i in ribo_free_idx if not i in sp_rst_idx]
    if len(ribo_free_exclude_sp_rst_index) > 0:
        custom_nb_force.addInteractionGroup(nc_atom_index, ribo_free_exclude_sp_rst_index)

    if stage == 1 or stage == 2:
        custom_nb_force.addInteractionGroup(nc_atom_index, AtR_atom_index)

    # A-site resid 76 (last residue) ribose R 
    AtR_id76_R_index = 0
    for res in top.residues():
        if res.chain.id == 'AtR':
            AtR_id76_res = res
    for atom in AtR_id76_res.atoms():
        if atom.name == 'R':
            AtR_id76_R_index = atom.index

    # P-site resid 76 (last residue) ribose R 
    PtR_id76_R_index = 0
    for res in top.residues():
        if res.chain.id == 'PtR':
            PtR_id76_res = res
    for atom in PtR_id76_res.atoms():
        if atom.name == 'R':
            PtR_id76_R_index = atom.index

    # FF parameters for bond interaction between tRNA and nascent chain
    bond_harmonic_force = 200*kilocalories/mole/angstroms**2
    angle_harmonic_force = 25*kilocalories/mole/radian**2
    improper_dihedral_force = 25*kilocalories/mole/radian**2
    d_R_N_A = 4.27*angstroms
    d_R_N_P = 4.76*angstroms
    a_PU2_R_N_A = 127*degree
    a_PU2_R_N_P = 130*degree
    a_P_R_N_A = 106*degree
    a_P_R_N_P = 117*degree
    di_N_R_P_PU2_A = 128*degree
    di_N_R_P_PU2_P = -161*degree
    # END FF parameters for bond interaction between tRNA and nascent chain
    
    for force in system.getForces():
        if force.getName() == 'HarmonicBondForce':
            hbf = force
        elif force.getName() == 'CustomAngleForce':
            caf = force
        elif force.getName() == 'PeriodicTorsionForce':
            ptf = force
        elif force.getName() == 'CustomTorsionForce':
            ctf = force

    if stage == 1:
        # delete bond, angle, dihedral energy term involving new AA within nascent chain
        if nascent_chain_length > 1:
            system.removeConstraint(nascent_chain_length-2)
        if nascent_chain_length > 2:
            caf.setAngleParameters(nascent_chain_length-3, nascent_chain_length-3, nascent_chain_length-2, 
                nascent_chain_length-1, [0.0, 0.0, 0.0, 0.0, 1e10, 0.0])
        if nascent_chain_length > 3:
            for i in range(4*(nascent_chain_length-4), 4*(nascent_chain_length-3)):
                ptf.setTorsionParameters(i, nascent_chain_length-4, nascent_chain_length-3, 
                    nascent_chain_length-2, nascent_chain_length-1, i%4+1, 0, 0)

        # add bonds between new AA and A-site resid 76 ribose R
        hbf.addBond(nascent_chain_length-1, AtR_id76_R_index, d_R_N_A, bond_harmonic_force)
        haf = HarmonicAngleForce()
        # add Ep angle for new AA -- AtR:76@R -- AtR:76@P
        haf.addAngle(nascent_chain_length-1, AtR_id76_R_index, AtR_id76_R_index-1, a_P_R_N_A, angle_harmonic_force)
        # add Ep angle for new AA -- AtR:76@R -- AtR:76@PU2
        haf.addAngle(nascent_chain_length-1, AtR_id76_R_index, AtR_id76_R_index+2, a_PU2_R_N_A, angle_harmonic_force)
        system.addForce(haf)
        # add improper dihedral potential for new AA -- AtR:76@R -- AtR:76@P -- AtR:76@PU2 
        ctf.addTorsion(nascent_chain_length-1, AtR_id76_R_index, AtR_id76_R_index-1, AtR_id76_R_index+2, 
            [improper_dihedral_force, di_N_R_P_PU2_A])

        # add bonds between previous AA and P-site resid 76 ribose R
        if nascent_chain_length > 1:
            hbf.addBond(nascent_chain_length-2, PtR_id76_R_index, d_R_N_P, bond_harmonic_force)
            # add Ep angle for previous AA -- PtR:76@R -- PtR:76@P
            haf.addAngle(nascent_chain_length-2, PtR_id76_R_index, PtR_id76_R_index-1, a_P_R_N_P, angle_harmonic_force)
            # add Ep angle for previous AA -- PtR:76@R -- PtR:76@PU2
            haf.addAngle(nascent_chain_length-2, PtR_id76_R_index, PtR_id76_R_index+2, a_PU2_R_N_P, angle_harmonic_force)
            # add improper dihedral potential for previous AA -- PtR:76@R -- PtR:76@P -- PtR:76@PU2 
            ctf.addTorsion(nascent_chain_length-2, PtR_id76_R_index, PtR_id76_R_index-1, PtR_id76_R_index+2, 
                [improper_dihedral_force, di_N_R_P_PU2_P])

        # add Ep angle for previous previous AA -- previous AA -- PtR:76@R
        if nascent_chain_length > 2:
            caf.addAngle(nascent_chain_length-3, nascent_chain_length-2, PtR_id76_R_index, 
                [106.4*kilocalories/mole/radian**2, 91.7*degree, 26.3*kilocalories/mole/radian**2, 
                130*degree, 0.1*mole/kilocalories, 4.3*kilocalories/mole])

        # add NB interactions between new AA and adjacent AA by setting exclusion to be invalid
        if nascent_chain_length == 2:
            custom_nb_force.setExclusionParticles(0, 0, 0)
        elif nascent_chain_length > 2:
            n = int(2*(nascent_chain_length-2))
            custom_nb_force.setExclusionParticles(n, nascent_chain_length-1, nascent_chain_length-1)
            custom_nb_force.setExclusionParticles(n-1, nascent_chain_length-2, nascent_chain_length-2)
        # add exclusion for NB between new AA and A-site resid 76 ribose R
        custom_nb_force.addExclusion(nascent_chain_length-1, AtR_id76_R_index)
        # add exclusion for NB between previous AA and P-site resid 76 ribose R
        if nascent_chain_length > 1:
            custom_nb_force.addExclusion(nascent_chain_length-2, PtR_id76_R_index)
        # add exclusion for NB between previous previous AA and P-site resid 76 ribose R
        if nascent_chain_length > 2:
            custom_nb_force.addExclusion(nascent_chain_length-3, PtR_id76_R_index)
    elif stage == 2:
        # add bonds between new AA and A-site resid 76 ribose R
        hbf.addBond(nascent_chain_length-1, AtR_id76_R_index, d_R_N_A, bond_harmonic_force)
        if nascent_chain_length > 1:
            system.removeConstraint(nascent_chain_length-2)
            hbf.addBond(nascent_chain_length-2, nascent_chain_length-1, 3.81*angstroms, 
                bond_harmonic_force)
        haf = HarmonicAngleForce()
        # add Ep angle for new AA -- AtR:76@R -- AtR:76@P
        haf.addAngle(nascent_chain_length-1, AtR_id76_R_index, AtR_id76_R_index-1, a_P_R_N_A, angle_harmonic_force)
        # add Ep angle for new AA -- AtR:76@R -- AtR:76@PU2
        haf.addAngle(nascent_chain_length-1, AtR_id76_R_index, AtR_id76_R_index+2, a_PU2_R_N_A, angle_harmonic_force)
        system.addForce(haf)
        # add improper dihedral potential for new AA -- AtR:76@R -- AtR:76@P -- AtR:76@PU2
        ctf.addTorsion(nascent_chain_length-1, AtR_id76_R_index, AtR_id76_R_index-1, AtR_id76_R_index+2, 
            [improper_dihedral_force, di_N_R_P_PU2_A])
        # add Ep angle for previous AA -- new AA -- AtR:76@R
        if nascent_chain_length > 1:
            caf.addAngle(nascent_chain_length-2, nascent_chain_length-1, AtR_id76_R_index, 
                [106.4*kilocalories/mole/radian**2, 91.7*degree, 26.3*kilocalories/mole/radian**2, 
                130*degree, 0.1*mole/kilocalories, 4.3*kilocalories/mole])
        # add exclusion for NB between new AA and A-site resid 76 ribose R
        custom_nb_force.addExclusion(nascent_chain_length-1, AtR_id76_R_index)
        # add exclusion for NB between previous AA and A-site resid 76 ribose R
        if nascent_chain_length > 1:
            custom_nb_force.addExclusion(nascent_chain_length-2, AtR_id76_R_index)
    elif stage == 3:
        # add bonds between new AA and P-site resid 76 ribose R
        hbf.addBond(nascent_chain_length-1, PtR_id76_R_index, d_R_N_P, bond_harmonic_force)

        haf = HarmonicAngleForce()
        # add Ep angle for new AA -- PtR:76@R -- PtR:76@P
        haf.addAngle(nascent_chain_length-1, PtR_id76_R_index, PtR_id76_R_index-1, a_P_R_N_P, angle_harmonic_force)
        # add Ep angle for new AA -- PtR:76@R -- PtR:76@PU2
        haf.addAngle(nascent_chain_length-1, PtR_id76_R_index, PtR_id76_R_index+2, a_PU2_R_N_P, angle_harmonic_force)
        system.addForce(haf)

        # add improper dihedral potential for new AA -- PtR:76@R -- PtR:76@P -- PtR:76@PU2
        ctf.addTorsion(nascent_chain_length-1, PtR_id76_R_index, PtR_id76_R_index-1, PtR_id76_R_index+2, 
            [improper_dihedral_force, di_N_R_P_PU2_P])

        # add Ep angle for previous AA -- new AA -- PtR:76@R
        if nascent_chain_length > 1:
            caf.addAngle(nascent_chain_length-2, nascent_chain_length-1, PtR_id76_R_index, 
                [106.4*kilocalories/mole/radian**2, 91.7*degree, 26.3*kilocalories/mole/radian**2, 
                130*degree, 0.1*mole/kilocalories, 4.3*kilocalories/mole])
        # add exclusion for NB between new AA and P-site resid 76 ribose R
        custom_nb_force.addExclusion(nascent_chain_length-1, PtR_id76_R_index)
        # add exclusion for NB between previous AA and P-site resid 76 ribose R
        if nascent_chain_length > 1:
            custom_nb_force.addExclusion(nascent_chain_length-2, PtR_id76_R_index)
    elif stage == 5:
        xref = (x_eject-2)*angstrom
        k = 20*kilocalories/mole/angstroms**2
        force_2 = CustomExternalForce("k*r^2; r=min(x-x0, 0)")
        force_2.addPerParticleParameter("k")
        force_2.addPerParticleParameter("x0")
        for atom in top.atoms():
            if atom.residue.chain.id == 'A':
                force_2.addParticle(atom.index, [k, xref])
        system.addForce(force_2)
    
    # add spherical restraint
    k = 0.1*kilocalories/mole/angstroms**2
    R0 = spherical_restraint_radius * angstrom
    center_xyz = spherical_restraint_center * angstrom
    force = CustomExternalForce("k*dR^2; dR=max(R-R0, 0); R=sqrt((x-x0)^2+(y-y0)^2+(z-z0)^2);")
    force.addGlobalParameter('k', k)
    force.addGlobalParameter('R0', R0)
    force.addGlobalParameter('x0', center_xyz[0])
    force.addGlobalParameter('y0', center_xyz[1])
    force.addGlobalParameter('z0', center_xyz[2])
    for atom in top.atoms():
        if atom.index in sp_rst_idx:
            force.addParticle(atom.index, [])
    system.addForce(force)
    
    # add position restraints
    force_7 = CustomExternalForce("k*((x-x0)^2+(y-y0)^2+(z-z0)^2)")
    force_7.addPerParticleParameter("k")
    force_7.addPerParticleParameter("x0")
    force_7.addPerParticleParameter("y0")
    force_7.addPerParticleParameter("z0")
    system.addForce(force_7)
    # END add position restraints
    
    # Remove ligand bond constraints
    try:
        rm_cons_LIG(system, rnc_psf_pmd, forcefield, top, template_map)
    except Exception as e:
        traceback.print_exc()
        sys.exit()

    return system
# END create system for elongation

# calculate minimum distance between nascent chain and ribosome 
def calc_min_distance(top, current_rnc_cor):
    dis_1 = 999999999999
    dis_2 = 999999999999
    ribo_atom_index = []
    nc_atom_index = []
    for atom in top.atoms():
        if atom.residue.chain.id == 'A':
            nc_atom_index.append(atom.index)
        elif atom.residue.chain.id != 'LIG':
            # not nascent chain and not ligands
            ribo_atom_index.append(atom.index)
    for i in nc_atom_index:
        coor_1 = current_rnc_cor[i].value_in_unit(angstroms)
        d = coor_1[0]
        if d < dis_2:
            dis_2 = d
        for j in ribo_atom_index:
            coor_2 = current_rnc_cor[j].value_in_unit(angstroms)
            d = ((coor_1[0]-coor_2[0])**2 + (coor_1[1]-coor_2[1])**2 + (coor_1[2]-coor_2[2])**2)**0.5
            if d < dis_1:
                dis_1 = d
    return (dis_1, dis_2)
    
def calc_NC_COM(top, current_rnc_cor, system):
    nc_atom_index = []
    for atom in top.atoms():
        if atom.residue.chain.id == 'A':
            nc_atom_index.append(atom.index)
    com = np.zeros(3)
    total_mass = 0
    for i in nc_atom_index:
        coor = current_rnc_cor[i].value_in_unit(angstroms)
        mass = system.getParticleMass(i).value_in_unit(dalton)
        com += coor * mass
        total_mass += mass
    com = com / total_mass
    return com

# remove bond constraints of 0 mass atoms
def rm_cons_0_mass(system):
    for force in system.getForces():
        if force.getName() == 'HarmonicBondForce':
            hbf = force
            break
    
    tag = 0
    while tag == 0 and system.getNumConstraints() != 0:
        for i in range(system.getNumConstraints()):
            con_i = system.getConstraintParameters(i)[0]
            con_j = system.getConstraintParameters(i)[1]
            mass_i = system.getParticleMass(con_i).value_in_unit(dalton)
            mass_j = system.getParticleMass(con_j).value_in_unit(dalton)
            if mass_i == 0 and mass_j == 0:
                system.removeConstraint(i)
                #print('Constraint %d is removed, range is %d'%(i, system.getNumConstraints()))
                tag = 0
                break
            elif mass_i == 0 or mass_j == 0:
                system.removeConstraint(i)
                #print('Constraint %d is removed, range is %d'%(i, system.getNumConstraints()))
                hbf.addBond(con_i, con_j, 3.81*angstroms, 50*kilocalories/mole/angstroms**2)
                tag = 0
                break
            else:
                tag = 1
# END remove bond constraints of 0 mass atoms

# remove bond constraints of LIG atoms
def rm_cons_LIG(system, psf_pmd, forcefield, top, templete_map):
    system_new = forcefield.createSystem(top, nonbondedMethod=CutoffNonPeriodic,
                 nonbondedCutoff=2.0*nanometer,
                 constraints=None, removeCMMotion=False, ignoreExternalBonds=True, 
                 residueTemplates=templete_map)
    for force in system_new.getForces():
        if force.getName() == 'HarmonicBondForce':
            bond_force = force
            break
    bond_parameter_list = [bond_force.getBondParameters(i) for i in range(bond_force.getNumBonds())]
    for force in system.getForces():
        if force.getName() == 'HarmonicBondForce':
            hbf = force
            break
    tag = 0
    while tag == 0 and system.getNumConstraints() != 0:
        for i in range(system.getNumConstraints()):
            con_i = system.getConstraintParameters(i)[0]
            con_j = system.getConstraintParameters(i)[1]
            segid_i = psf_pmd.atoms[con_i].residue.segid
            segid_j = psf_pmd.atoms[con_j].residue.segid
            if segid_i == 'LIG' and segid_j == 'LIG':
                system.removeConstraint(i)
                # print('Constraint %d is removed, range is %d'%(i, system.getNumConstraints()))
                for bp in bond_parameter_list:
                    if (con_i == bp[0] and con_j == bp[1]) or (con_i == bp[1] and con_j == bp[0]):
                        hbf.addBond(*bp)
                        break
                tag = 0
                break
            else:
                tag = 1
# END remove bond constraints of LIG atoms

# energy decomposition 
def forcegroupify(system):
    forcegroups = {}
    for i in range(system.getNumForces()):
        force = system.getForce(i)
        force.setForceGroup(i)
        f = str(type(force))
        s = f.split('\'')
        f = s[1]
        s = f.split('.')
        f = s[-1]
        forcegroups[i] = f
    return forcegroups

def getEnergyDecomposition(handle, context, forcegroups):
    energies = {}
    for i, f in forcegroups.items():
        try:
            states = context.getState(getEnergy=True, groups={i})
        except ValueError as e:
            print(str(e))
            energies[i] = Quantity(np.nan, kilocalories/mole)
        else:
            energies[i] = states.getPotentialEnergy()
    results = energies
    handle.write('    Potential Energy:\n')
    for idd in energies.keys():
        handle.write('      %s: %.4f kcal/mol\n'%(forcegroups[idd], energies[idd].value_in_unit(kilocalories/mole))) 
    return results

def getMaxForce(handle, context, system):
    forcegroups = forcegroupify(system)
    forces = {}
    for i, f in forcegroups.items():
        states = context.getState(getForces=True, groups={i})
        f_array = states.getForces(asNumpy=True)._value
        f_v_array = numpy.linalg.norm(f_array, axis=1)
        forces[i] = numpy.max(f_v_array)
        
    results = forces
    handle.write('    Maximum Force:\n')
    for idd in forces.keys():
        handle.write('      %s: %.4f\n'%(forcegroups[idd], forces[idd])) 
    return results
# END energy decomposition 

# format psf generated from parmed so that it can be read by vmd
def formate_psf_vmd(psf_file):
    f = open(psf_file, 'r')
    f_o = open('new_'+psf_file, 'w')
    section = None
    for line in f:
        if not line.strip():
            section = None
            f_o.write(line)
            continue
        if '!NATOM' in line:
            section = 'ATOM'
            f_o.write(line)
            continue
        if '!NBOND' in line:
            section = 'LEFT'
            f_o.write(line)
            continue
        if section == 'ATOM':
            if line[47:53].strip().isdigit():
                f_o.write('%10d %-8s %-8i %-8s %-8s %4d %10.5f %13.3f    \n' % (
                    int(line[0:10].strip()),
                    line[11:19].strip(),
                    int(line[20:28].strip()),
                    line[29:37].strip(),
                    line[38:46].strip(),
                    int(line[47:53].strip()),
                    float(line[54:64].strip()),
                    float(line[65:78].strip())))
            else:
                f_o.write('%10d %-8s %-8i %-8s %-8s %-4s %10.5f %13.3f    \n' % (
                    int(line[0:10].strip()),
                    line[11:19].strip(),
                    int(line[20:28].strip()),
                    line[29:37].strip(),
                    line[38:46].strip(),
                    line[47:53].strip(),
                    float(line[54:64].strip()),
                    float(line[65:78].strip())))
        else:
            f_o.write(line)
    f.close()
    f_o.close()
    os.system('rm -f '+psf_file)
    os.system('mv '+'new_'+psf_file+' '+psf_file)
# END format psf for vmd

###### convert time seconds to hours ######
def convert_time(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return ("%d:%02d:%02d"%(h, m, s))
###### END convert time seconds to hours ######

# function to sample a first passage time from an
# exponential distribution with the requested mean
# value; units are 0.015 ps integration time steps
def sample_fpt_dist(mfptaa):
    #r1 = random.uniform(0,1)
    #return (r1, -np.log(r1)*np.float64(mfptaa))
    return random.expovariate(1/mfptaa)
# END #
# Auto-combine ribosome and protein parameter files
def combine_ribo_prot_param(ribo_param_file, prot_param_file):
    param_str_list = []
    section = None
    string = ''
    f_r = open(ribo_param_file, 'r')
    for line in f_r:
        line = line.strip()
        if not line:
            # This is a blank line
            continue
        if line.startswith('*'):
            # This is a comment line
            continue
        if line.startswith('ATOM'):
            section = 'ATOM'
            string = line + '\n'
            continue
        if line.startswith('BOND'):
            param_str_list.append(string)
            section = 'BOND'
            string = line + '\n'
            continue
        if line.startswith('ANGLE'):
            param_str_list.append(string)
            section = 'ANGLE'
            string = line + '\n'
            continue
        if line.startswith('DIHEDRAL'):
            param_str_list.append(string)
            section = 'DIHEDRAL'
            string = line + '\n'
            continue
        if line.startswith('IMPHI'):
            param_str_list.append(string)
            section = 'IMPHI'
            string = line + '\n'
            continue
        if line.startswith('NONBONDED'):
            param_str_list.append(string)
            section = 'NONBONDED'
            string = line + '\n'
            continue
        if line.startswith('CUTNB'):
            string += line + '\n'
            continue
        if line.startswith('NBFIX'):
            param_str_list.append(string)
            section = 'NBFIX'
            string = line + '\n'
            continue
        # It seems like files? sections? can be terminated with 'END'
        if line.startswith('END'):
            param_str_list.append(string)
            section = None
            continue
        # If we have no section, skip
        if section is None: continue
        # Now handle each section specifically
        elif section == 'ATOM':
            words = line.split()
            string += 'MASS %-5s %-8s %.6f\n'%(str(words[1]), words[2], float(words[3]))
        else:
            string += line + '\n'
    f_r.close()

    section = None
    f_p = open(prot_param_file, 'r')
    for line in f_p:
        line = line.strip()
        if not line:
            # This is a blank line
            continue
        if line.startswith('*') or line.startswith('!'):
            # This is a comment line
            continue
        if line.startswith('ATOM'):
            section = 0
            last_mass_index = int(param_str_list[0].split('MASS')[-1].strip().split()[0])
            continue
        if line.startswith('BOND'):
            section = 1
            continue
        if line.startswith('ANGLE'):
            section = 2
            continue
        if line.startswith('DIHEDRAL'):
            section = 3
            continue
        if line.startswith('IMPHI'):
            section = 4
            continue
        if line.startswith('NONBONDED'):
            section = 5
            continue
        if line.startswith('CUTNB'):
            continue
        if line.startswith('NBFIX'):
            section = 6
            continue
        # It seems like files? sections? can be terminated with 'END'
        if line.startswith('END'):
            section = None
            continue
        # If we have no section, skip
        if section is None: continue
        # Now handle each section specifically
        elif section == 0:
            words = line.split()
            param_str_list[0] += 'MASS %-5s %-8s %.6f\n'%(str(last_mass_index+int(words[1])), words[2], float(words[3]))
        else:
            param_str_list[section] += line + '\n'
    f_p.close()
    
    prefix = '/'.join(ribo_param_file.strip().split('/')[:-1])
    # rnc_prm_file = prefix+'/rnc_%s.prm'%(time.time())
    rnc_prm_file = prefix+'/rnc_%d-%d.prm'%(start_traj_id, start_traj_id+num_traj-1)
    f = open(rnc_prm_file, 'w')
    f.write('* This CHARMM .prm file describes a Go model of nascent chain and ribosome structure\n*\n\n')
    for i in range(len(param_str_list)):
        f.write(param_str_list[i]+'\n')
    f.write('END\n')
    f.close()
    
    return rnc_prm_file
# END Auto-combine ribosome and protein parameter files

# parse mask
def parse_mask(struct, mask):
    mask_idx = []
    mask_list = mask.strip().split('|')
    for m in mask_list:
        sub_list = m.strip().split(':')
        seg_mask = sub_list[0]
        segid_list = seg_mask.strip().split(',')
        segid_list = [s.strip() for s in segid_list]
        if len(sub_list) == 2:
            sub_mask = sub_list[1]
            sub_list = sub_mask.strip().split('@')
            res_mask = sub_list[0]
            resid_list =res_mask.strip().split(',')
            resid_list = [s.strip().split(' - ') for s in resid_list]
            if len(sub_list) == 2:
                atm_mask = sub_list[1]
                atmnm_list =atm_mask.strip().split(',')
                atmnm_list = [s.strip() for s in atmnm_list]
            else:
                atmnm_list = []
        else:
            resid_list = []
            atmnm_list = []

        for atm in struct.atoms:
            if (atm.residue.segid in segid_list and atm.name in atmnm_list) or (segid_list == [] and atmnm_list == []) or (
                segid_list == [] and atm.name in atmnm_list) or (atm.residue.segid in segid_list and atmnm_list == []):
                resid = atm.residue.number
                if resid_list == []:
                    mask_idx.append(atm.idx)
                    continue
                for r in resid_list:
                    if len(r) == 1 and resid == int(r[0]):
                        mask_idx.append(atm.idx)
                        break
                    elif len(r) == 2 and resid >= int(r[0]) and resid <= int(r[1]):
                        mask_idx.append(atm.idx)
                        break                
    return mask_idx
# END parse mask

##################################### MAIN #######################################
ctrlfile = ''

if len(sys.argv) == 1:
    print(usage)
    sys.exit()

try:
    opts, args = getopt.getopt(sys.argv[1:],"hf:", ["ctrlfile="])
except getopt.GetoptError:
    print(usage)
    sys.exit()
for opt, arg in opts:
    if opt == '-h':
        print(usage)
        sys.exit()
    elif opt in ("-f", "--ctrlfile"):
        ctrlfile = arg

use_gpu = 0 # whether to use gpu (0 use cpu; 1 use gpu)
tpn = 20 # total number of processors
ppn = 1 # number of processors for each trajectory
start_traj_id = 1 # trajectory id to start
num_traj = 100 # total number of trajectories
temp_prod = 310.0 * kelvin # temperature of equilibrium simulation
restart = 0 # flag of whether run restart
log_file = 'info.log' # log file name
prot_psf = '' # Charmm psf file for CG protein model
prot_top = '' # Charmm top file for CG protein model
prot_param = '' # Charmm prm file for CG protein model
ribo_psf = '' # Charmm psf file for CG protein model
ribo_top = '' # Charmm top file for CG protein model
ribo_param = '' # Charmm prm file for CG protein model
starting_strucs = '' # starting structures (Charmm cor file)
start_nascent_chain_length = 1 # start residue for elongation, ignored when restart = 1
total_nascent_chain_length = 0 # total residue for elongation
mrna_seq = '' # path to file containing codon sequence for this protein, ignored when uniform_ta = 0
trans_times = '' # path to file containing codon:translation time pairs, ignored when uniform_ta = 0
uniform_ta = 0 # flag for whether (1) or not (0) we want to use a constant translation time
uniform_mfpt = 0 # value for the mean translation time to use when uniform_ta = 1
ribo_free_mask = '' # ribosomal atoms set to be free. This means that you must have corresponding cg force field parameters 
                    # in ribosome prm file. Amber-like mask string is accepted. For example, selection block "L24 : 42 - 59" 
                    # will select all atoms in resid 42 to 59 of segid L24. Use ":" to select residue number and "@" to 
                    # select atom name. Use " - " to select a range of residues (space required) and "," to select multiple 
                    # individual residue. Use "|" to seperate multiple selection blocks.
time_stage_1 = 0.68/1000 # experimental mean dwell time (s) before peptide bond formation
time_stage_2 = 8.38/1000 # experimental mean dwell time (s) before tRNA translocation
ribosome_traffic = 0 # flag for considering ribosome traffic effect on translation time. 0: turn off; 1: turn on
initiation_rate = 0 # translation initiation rate for ribosome traffic calculation
x_eject = 60 # x-axis threshold to determine whether nascant chain has ejected from ribosome in angstrom
scale_factor = 4375901 # scale factor used to scale experimental translation time (s) to in silico translation time (ns) 
                       # by experimental_translation_time (ns) / scale_factor
spherical_restraint_mask = '' # Molecules to be restained within a shpere;
spherical_restraint_center = [0, 0, 0] # [x, y, z] coordinates for spherical center in angstrom
spherical_restraint_radius = 100 # Spherical radius in angstrom
nsteps_save = 5000 # save .out and .dcd each nsteps_save steps
timestep = 0.015*picoseconds # time step for simulation
fbsolu = 0.05/picosecond
nonbond_cutoff = 2.0*nanometer
switch_cutoff = 1.8*nanometer
constraint_tolerance = 1e-10
sleep_time = 5 # how often (seconds) the main process check and write the log file

if not os.path.exists(ctrlfile):
    print('Error: cannot find control file ' + ctrlfile + '.')
    sys.exit()

file_object = open(ctrlfile,'r')
try:
    for line in file_object:
        line = line.strip()
        if not line:
            # This is a blank line
            continue
        if line.startswith('#'):
            # This is a comment line
            continue
        if line.startswith('use_gpu'):
            words = line.split('=')
            use_gpu = int(words[1].strip())
            continue
        if line.startswith('tpn'):
            words = line.split('=')
            tpn = int(words[1].strip())
            continue
        if line.startswith('ppn'):
            words = line.split('=')
            ppn = int(words[1].strip())
            continue
        if line.startswith('start_traj_id'):
            words = line.split('=')
            start_traj_id = int(words[1].strip())
            continue
        if line.startswith('num_traj'):
            words = line.split('=')
            num_traj = int(words[1].strip())
            continue
        if line.startswith('temp_prod'):
            words = line.split('=')
            temp_prod = float(words[1].strip()) * kelvin
            continue
        if line.startswith('restart'):
            words = line.split('=')
            restart = int(words[1].strip())
            continue
        if line.startswith('log_file'):
            words = line.split('=')
            log_file = words[1].strip()
            continue
        if line.startswith('prot_psf'):
            words = line.split('=')
            prot_psf = words[1].strip()
            continue
        if line.startswith('prot_top'):
            words = line.split('=')
            prot_top = words[1].strip()
            continue
        if line.startswith('prot_param'):
            words = line.split('=')
            prot_param = words[1].strip()
            continue
        if line.startswith('ribo_psf'):
            words = line.split('=')
            ribo_psf = words[1].strip()
            continue
        if line.startswith('ribo_top'):
            words = line.split('=')
            ribo_top = words[1].strip()
            continue
        if line.startswith('ribo_param'):
            words = line.split('=')
            ribo_param = words[1].strip()
            continue
        if line.startswith('starting_strucs'):
            words = line.split('=')
            starting_strucs = words[1].strip()
            continue
        if line.startswith('start_nascent_chain_length'):
            words = line.split('=')
            start_nascent_chain_length = int(words[1].strip())
            continue
        if line.startswith('total_nascent_chain_length'):
            words = line.split('=')
            total_nascent_chain_length = int(words[1].strip())
            continue
        if line.startswith('mrna_seq'):
            words = line.split('=')
            mrna_seq = words[1].strip()
            continue
        if line.startswith('trans_times'):
            words = line.split('=')
            trans_times = words[1].strip()
            continue
        if line.startswith('uniform_ta'):
            words = line.split('=')
            uniform_ta = int(words[1].strip())
            continue
        if line.startswith('uniform_mfpt'):
            words = line.split('=')
            uniform_mfpt = float(words[1].strip())
            continue
        if line.startswith('ribo_free_mask'):
            words = line.split('=')
            ribo_free_mask = words[1].strip()
            continue
        if line.startswith('time_stage_1'):
            words = line.split('=')
            time_stage_1 = float(words[1].strip())
            continue
        if line.startswith('time_stage_2'):
            words = line.split('=')
            time_stage_2 = float(words[1].strip())
            continue
        if line.startswith('x_eject'):
            words = line.split('=')
            x_eject = float(words[1].strip())
            continue
        if line.startswith('ribosome_traffic'):
            words = line.split('=')
            ribosome_traffic = int(words[1].strip())
            continue
        if line.startswith('initiation_rate'):
            words = line.split('=')
            initiation_rate = float(words[1].strip())
            continue
        if line.startswith('scale_factor'):
            words = line.split('=')
            scale_factor = float(words[1].strip())
            continue
        if line.startswith('spherical_restraint_mask'):
            words = line.split('=')
            spherical_restraint_mask = words[1].strip()
            continue
        if line.startswith('spherical_restraint_center'):
            words = line.split('=')
            spherical_restraint_center = [float(s) for s in words[1].strip().split()]
            continue
        if line.startswith('spherical_restraint_radius'):
            words = line.split('=')
            spherical_restraint_radius = float(words[1].strip())
            continue
finally:
     file_object.close()

###### Check Control Parameters ######
if use_gpu != 0 and use_gpu != 1:
    print('Error: use_gpu can only be set as 0 (use cpu) or 1 (use gpu)')
    sys.exit()
if tpn == 0:
    print('Error: no processor number specified.')
    sys.exit()
if ppn == 0:
    print('Error: no processor number for each trajectory specified.')
    sys.exit()
if tpn%ppn != 0:
    print('Error: tpn is not the multiple of ppn.')
    sys.exit()
if num_traj == 0:
    print('Error: no trajectory number specified.')
    sys.exit()
if prot_psf == '':
    print('Error: no Charmm psf file specified for protein.')
    sys.exit()
if prot_top == '':
    print('Error: no Charmm top file specified for protein.')
    sys.exit()
if prot_param == '':
    print('Error: no Charmm prm file specified for protein.')
    sys.exit()
if ribo_psf == '':
    print('Error: no Charmm psf file specified for ribosome.')
    sys.exit()
if ribo_top == '':
    print('Error: no Charmm top file specified for ribosome.')
    sys.exit()
if ribo_param == '':
    print('Error: no Charmm prm file specified for ribosome.')
    sys.exit()
if starting_strucs == '':
    print('Error: no starting structures specified.')
    sys.exit()
if start_nascent_chain_length <= 0:
    print('Error: wrong start nascent chain length specified.')
    sys.exit()
if total_nascent_chain_length < start_nascent_chain_length:
    print('Error: wrong total nascent chain length specified.')
    sys.exit()
if restart != 0 and restart != 1:
    print('Error: restart can only be 0 (no restart) or 1 (restart).')
    sys.exit()
if uniform_ta == 0:
    if mrna_seq == '':
        print('Error: no mrna_seq specified when uniform_ta = 0.')
        sys.exit()
    if trans_times == '':
        print('Error: no trans_times specified when uniform_ta = 0.')
        sys.exit()
elif uniform_ta == 1:
    if uniform_mfpt == 0:
        print('Error: no uniform_mfpt specified when uniform_ta = 1.')
        sys.exit()
else:
    print('Error: uniform_ta can only be set to 0 or 1.')
    sys.exit()
if ribosome_traffic == 1 and uniform_ta == 1:
    print('Error: ribosome traffic cannot currently be used for uniform translation time')
    sys.exit()
if ribosome_traffic == 1:
    if initiation_rate <= 0:
        print('Error: wrong initiation_rate value '+str(initiation_rate))
        sys.exit()
elif not ribosome_traffic == 0:
    print('Error: ribosome_traffic can only be set to 0 or 1.')
    sys.exit()

start_res = [start_nascent_chain_length for i in range(num_traj)]

ribo_psf_pmd = pmd.charmm.psf.CharmmPsfFile(ribo_psf)
prot_psf_pmd = pmd.charmm.psf.CharmmPsfFile(prot_psf)
if restart == 1:
    for i in range(1, num_traj + 1):
        traj_id = start_traj_id + i -1
        if os.path.exists('output/'+str(traj_id)+'.out'):
            last_nc = 0
            tag_done = 0
            f = open('output/'+str(traj_id)+'.out', 'r')
            for line in f:
                if line.startswith('--> Elongation finished at length '):
                    words = line.strip().split()
                    last_nc = int(words[5])
                elif line.startswith('--> All Done'):
                    tag_done = 1
            f.close()
            if tag_done == 0:
                if last_nc == len(prot_psf_pmd.residues):
                    start_res[i-1] = last_nc
                else:
                    start_res[i-1] = last_nc + 1
            else:
                start_res[i-1] = len(prot_psf_pmd.residues) + 1
            
            if last_nc == 0:
                os.system('rm -f output/'+str(traj_id)+'.out')
            elif tag_done == 0:
                f = open('output/'+str(traj_id)+'.out', 'r')
                fo = open('output/new_'+str(traj_id)+'.out', 'w')
                for line in f:
                    fo.write(line)
                    if line.startswith('--> Elongation finished at length '+str(start_res[i-1]-1)):
                        break
                f.close()
                fo.close()
                os.system('rm -f output/'+str(traj_id)+'.out')
                os.system('mv output/new_'+str(traj_id)+'.out output/'+str(traj_id)+'.out')
                    
###### END Check Control Parameters ######

###### Setup writing log files ######
log_file_object = open(log_file,'w')
log_head = ''
log_head += 'Continuous Synthesis for CG Model using OpenMM\nAuthor: Yang Jiang; Dan Nissley; Ed O\'Brien.\n'
log_head += 'Start at '+time.asctime(time.localtime(time.time()))+'\n'
log_head += 'Total number of processors: '+str(tpn)+'\n'
log_head += 'Number of processors for each trajectory: '+str(ppn)+'\n'
log_head += 'Trajectories start at: '+str(start_traj_id)+'\n'
log_head += 'Number of trajectories: '+str(num_traj)+'\n'
log_head += 'Temperature of production simulation: '+str(temp_prod)+'\n'
log_head += 'Log file name: '+str(log_file)+'\n'
log_head += 'Protein psf file: '+str(prot_psf)+'\n'
log_head += 'Protein top file: '+str(prot_top)+'\n'
log_head += 'Protein prm file: '+str(prot_param)+'\n'
log_head += 'Ribosome psf file: '+str(ribo_psf)+'\n'
log_head += 'Ribosome top file: '+str(ribo_top)+'\n'
log_head += 'Ribosome prm file: '+str(ribo_param)+'\n'

if uniform_ta == 0:
    log_head += 'Codon traslation times will be used.\n'
    log_head += 'File for mRNA sequence of nascent chain: '+str(mrna_seq)+'\n'
    log_head += 'File for codon translation times: '+str(trans_times)+'\n'
else:
    log_head += 'Uniform traslation time will be used.\n'
    log_head += 'Mean translation steps: '+str(uniform_mfpt)+'\n'

log_head += 'Free part of ribosome: '+str(ribo_free_mask)+'\n'
log_head += 'Experimental dwell time for peptide bond formation: '+str(time_stage_1)+' s\n'
log_head += 'Experimental dwell time for tRNA translocation: '+str(time_stage_2)+' s\n'
log_head += 'x threshold for ejection: '+str(x_eject)+' Angstrom\n'

if spherical_restraint_mask != '':
    log_head += 'Molecules %s will be restrained within the sphere centered at %s with radius of %.4f Angstrom\n'%(spherical_restraint_mask, str(spherical_restraint_center), spherical_restraint_radius)
else:
    log_head += 'No spherical restraint applied\n'

if ribosome_traffic == 1:
    log_head += 'Ribosome traffic effect will be considered\n'
    log_head += 'Translation-initiation rate: '+str(initiation_rate)+' s-1\n'
else:
    log_head += 'Ribosome traffic effect will not be considered\n'

if restart == 0:
    log_head += 'No restart requested\n'
else:
    log_head += 'Restart requested\n'

log_head += 'Starting structure: '+starting_strucs+'\n'
log_head += 'File save steps: '+str(nsteps_save)+'\n'
log_head += 'Time step: '+str(timestep)+'\n'
log_head += 'Scaling factor: '+str(scale_factor)+'\n'

if not os.path.exists('output'):
    os.mkdir('output')
elif restart == 0:
    for i in range(num_traj):
        os.system('rm -f output/%d.out'%(i+start_traj_id))
if not os.path.exists('traj'):
    os.mkdir('traj')
elif restart == 0:
    for i in range(num_traj):
        os.system('rm -rf traj/%d/'%(i+start_traj_id))
###### END Setup writing log files ######

###### Initialize System #######
if len(prot_psf_pmd.residues) < total_nascent_chain_length:
    print('Warning: total_nascent_chain_length > protein length defined by psf.')
    total_nascent_chain_length = len(prot_psf_pmd.residues)
    print('Adjust total_nascent_chain_length to be '+str(total_nascent_chain_length))
log_head += 'Total nascent chain length: '+str(total_nascent_chain_length)+'\n'

# ribosome resid list
ribo_resid_list = []
for res in ribo_psf_pmd.residues:
    ribo_resid_list.append(res.number)

ribo_coor = pmd.load_file(starting_strucs)
restraint_coor = []
for idx, coor in enumerate(ribo_coor.positions):
    coor = coor.value_in_unit(angstroms)
    d = ((coor[0]-12)**2 + coor[1]**2 + coor[2]**2)**0.5
    if ribo_coor.segid[idx] != 'A' and ribo_coor.segid[idx] != 'AtR' and ribo_coor.segid[idx] != 'PtR' and d <= 12: 
        # select interaction sites around the peptidyl transferase center
        restraint_coor.append(coor)

previous_rnc_cor_list = []
for i in range(num_traj):
    if start_res[i] == 1 or restart == 0:
        previous_rnc_cor_list.append('../../'+starting_strucs)
    else:
        previous_rnc_cor_list.append('rnc_l'+str(start_res[i]-1)+'_stage_3_final.cor')

# combine ribosome forcefield with protein forcefield
rnc_prm_file = combine_ribo_prot_param(ribo_param, prot_param)
os.system('parse_cg_prm.py -t "'+ribo_top+' '+prot_top+'" -p '+rnc_prm_file)
forcefield = ForceField(rnc_prm_file.split('.prm')[0]+'.xml')
os.system('rm -f '+rnc_prm_file)
os.system('mv '+rnc_prm_file.split('.prm')[0]+'.xml '+('/'.join(ribo_param.strip().split('/')[:-1]))+'/rnc.xml')

# Build mean translation time list
real_mean_fpt_list = []
intrinsic_mean_fpt_list = []
if not mrna_seq == '':
    mrna_seq_file = mrna_seq
    f = open(mrna_seq)
    mrna_seq = f.read().strip().split('\n')
    mrna_seq = ''.join(mrna_seq)
    f.close()

    # check to see if the number of nucleotides read in is evenly divisible by 3
    if len(mrna_seq) % 3 != 0:
        print('Error: Number of nucleotides in sequence, '+str(len(mrna_seq))+', is not evenly divisible by 3')
        sys.exit()

    # check to make sure the number of codons in the mRNA is equal to max_res+1; 
    # that's one codon for each amino acid plus the stop codon
    if (len(mrna_seq)//3) != (len(prot_psf_pmd.residues)+1):
        print('Error: mRNA sequence length of '+str(len(mrna_seq)//3)+' codons does not match the max_res+1 value of '
            +str(len(prot_psf_pmd.residues)+1)+'\n')
        print('You must have one codon for each amino acid as well as a stop codon for a total of max_res+1 codons.')
        sys.exit()

if uniform_ta == 0:
    # make a dictionary to map codons to translation times
    map_codon_to_mfpt = {}
    # populate the map_codon_to_mfpt dictionary
    f = open(trans_times, 'r')
    for line in f:
        temp = line.strip().split()
        if len(temp) == 2:
            map_codon_to_mfpt[temp[0]] = float(temp[1])
    f.close()

    codon_list = []
    for nc in range(int(len(mrna_seq)/3)):
        codon = mrna_seq[3*nc]+mrna_seq[3*nc+1]+mrna_seq[3*nc+2]
        codon_list.append(codon)

    if ribosome_traffic == 1:
        mrna_seq_prefix = '/'.join(mrna_seq_file.strip().split('/')[:-1])
        mrna_data_file = mrna_seq_prefix+'/mrna_%d-%d.dat'%(start_traj_id, start_traj_id+num_traj-1)
        fo = open(mrna_data_file, 'w')
        fo.write(mrna_seq+'\n')
        fo.close()
        shell_out = os.popen('ribosome_traffic '+mrna_data_file+' '+trans_times+' '+str(initiation_rate)).readlines()
        # populate map_resid_to_codon with codon positon : codon type pairs
        print('AA insertion time (s) considering ribosome traffic:')
        for i in range(int(len(mrna_seq)/3)):
            codon = mrna_seq[3*i]+mrna_seq[3*i+1]+mrna_seq[3*i+2]
            real_mean_fpt_list.append(float(shell_out[i].strip()))
            intrinsic_mean_fpt_list.append(map_codon_to_mfpt[codon])
            print('%12.6f'%float(shell_out[i].strip()))
        os.system('rm -f '+mrna_data_file)
    else:
        for i in range(int(len(mrna_seq)/3)):
            codon = mrna_seq[3*i]+mrna_seq[3*i+1]+mrna_seq[3*i+2]
            intrinsic_mean_fpt_list.append(map_codon_to_mfpt[codon])
            real_mean_fpt_list.append(map_codon_to_mfpt[codon])
else:
    for i in range(len(prot_psf_pmd.residues)+1):
        intrinsic_mean_fpt_list.append(uniform_mfpt)
        real_mean_fpt_list.append(uniform_mfpt)
# END Build mean translation time list
# assign GPU device index
dev_index_list = []
if use_gpu != 0:
    if os.getenv('CUDA_VISIBLE_DEVICES') != None:
        dev_index_list = os.getenv('CUDA_VISIBLE_DEVICES').strip().split(',')
        dev_index_list = [int(d) for d in dev_index_list]
    elif os.getenv('PBS_GPUFILE') != None or os.getenv('PBS_GPUFILE') != '':
        gpu_file = open(os.getenv('PBS_GPUFILE'))
        dev_index_list = gpu_file.readlines()
        gpu_file.close()
        dev_index_list = [i for i in range(len(dev_index_list))]
    else:
        print('Error: No CUDA environment detected!')
        sys.exit()
    if len(dev_index_list) != int(tpn/ppn):
        print('Error: # of available GPU devices (%d) does not equal to tpn/ppn (%d)'%(len(dev_index_list), int(tpn/ppn)))
        sys.exit()

###### Continuous Synthesis ######
nprocess = int(tpn/ppn)
log_file_object = open(log_file, 'w')

log_head += '\n%10s %10s %20s %15s %10s %15s\n'%('SIM_ID', 'START_LEN', 'SIM_STATUS', 'CURRENT_LEN', 'TIME_USED', 'SPEED (ns/d)')
log_output = log_head
start_str = []
for i in range(1, num_traj + 1):
    start_str.append(str(start_res[i-1]))
    log_output += '%10s %10s %20s %15s %10s %15s\n'%(str(start_traj_id+i-1), start_str[i-1], 'wait', '--', '--', '--')
log_file_object.write(log_output)
log_file_object.close()

print('Setup process pool containing %d processors'%nprocess)
pool = multiprocessing.Pool(nprocess)
for i in range(1, num_traj + 1):
    pool.apply_async(run_elongation, (start_traj_id+i-1, start_res[i-1], total_nascent_chain_length, previous_rnc_cor_list[i-1], ))

start_time = [time.time() for i in range(num_traj)]
end_time = [time.time() for i in range(num_traj)]
while True:
    time.sleep(sleep_time)
    log_file_object = open(log_file,'w')
    log_output = log_head
    for i in range(1, num_traj + 1):
        if os.path.exists('output/'+str(start_traj_id+i-1)+'.out'):
            last_line = os.popen('grep "\\-\\-> Elongation at length" output/'+str(start_traj_id+i-1)+'.out | tail -n 1').read().strip()
            if not last_line:
                log_output += '%10s %10s %20s %15s %10s %15s\n'%(str(start_traj_id+i-1), start_str[i-1], 'wait', '--', '--', '--')
            else:
                words = last_line.split()
                current_length = int(words[4])
                last_line = os.popen('tail -n 1 output/'+str(start_traj_id+i-1)+'.out').read().strip()
                words = last_line.split()
                if last_line.startswith('--> All Done'):
                    status = 'Done'
                    speed = '--'
                    time_used = convert_time(end_time[i-1] - start_time[i-1])
                elif last_line.endswith('--> Elongation finished at length %d'%(start_res[i-1]-1)):
                    status = 'wait'
                    current_length = min([current_length+1, total_nascent_chain_length])
                    start_time[i-1] = time.time()
                    time_used = '--'
                    speed = '--'
                elif words[0].endswith('%'):
                    status = words[1]+'('+words[0]+')'
                    speed = str(float(words[5]))
                    end_time[i-1] = time.time()
                    time_used = convert_time(end_time[i-1] - start_time[i-1])
                else:
                    status = 'minimizing'
                    speed = '--'
                    end_time[i-1] = time.time()
                    time_used = convert_time(end_time[i-1] - start_time[i-1])
                log_output += '%10s %10s %20s %15s %10s %15s\n'%(str(start_traj_id+i-1), start_str[i-1], status, str(current_length),
                                                                 time_used, speed)
        else:
            start_time[i-1] = time.time()
            log_output += '%10s %10s %20s %15s %10s %15s\n'%(str(start_traj_id+i-1), start_str[i-1], 'wait', '--', '--', '--')
    log_file_object.write(log_output)
    log_file_object.close()

    if len(pool._cache) == 0:
        print('All Done.')
        break

pool.close()
pool.join()

