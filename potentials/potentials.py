import torch
import numpy as np 
from util import generate_Cbeta

class Potential:
    '''
        Interface class that defines the functions a potential must implement
    '''

    def compute(self, xyz):
        '''
            Given the current structure of the model prediction, return the current
            potential as a PyTorch tensor with a single entry

            Args:
                xyz (torch.tensor, size: [L,27,3]: The current coordinates of the sample
            
            Returns:
                potential (torch.tensor, size: [1]): A potential whose value will be MAXIMIZED
                                                     by taking a step along it's gradient
        '''
        raise NotImplementedError('Potential compute function was not overwritten')

class monomer_ROG(Potential):
    '''
        Radius of Gyration potential for encouraging monomer compactness

        Written by DJ and refactored into a class by NRB
    '''

    def __init__(self, weight=1, min_dist=15):

        self.weight   = weight
        self.min_dist = min_dist

    def compute(self, xyz):
        Ca = xyz[:,1] # [L,3]

        centroid = torch.mean(Ca, dim=0, keepdim=True) # [1,3]

        dgram = torch.cdist(Ca[None,...].contiguous(), centroid[None,...].contiguous(), p=2) # [1,L,1,3]

        dgram = torch.maximum(self.min_dist * torch.ones_like(dgram.squeeze(0)), dgram.squeeze(0)) # [L,1,3]

        rad_of_gyration = torch.sqrt( torch.sum(torch.square(dgram)) / Ca.shape[0] ) # [1]

        return -1 * self.weight * rad_of_gyration

class binder_ROG(Potential):
    '''
        Radius of Gyration potential for encouraging binder compactness

        Author: NRB
    '''

    def __init__(self, binderlen, weight=1, min_dist=15):

        self.binderlen = binderlen
        self.min_dist  = min_dist
        self.weight    = weight

    def compute(self, xyz):
        
        # Only look at binder residues
        Ca = xyz[:self.binderlen,1] # [Lb,3]

        centroid = torch.mean(Ca, dim=0, keepdim=True) # [1,3]

        # cdist needs a batch dimension - NRB
        dgram = torch.cdist(Ca[None,...].contiguous(), centroid[None,...].contiguous(), p=2) # [1,Lb,1,3]

        dgram = torch.maximum(self.min_dist * torch.ones_like(dgram.squeeze(0)), dgram.squeeze(0)) # [Lb,1,3]

        rad_of_gyration = torch.sqrt( torch.sum(torch.square(dgram)) / Ca.shape[0] ) # [1]

        return -1 * self.weight * rad_of_gyration


class dimer_ROG(Potential):
    '''
        Radius of Gyration potential for encouraging compactness of both monomers when designing dimers

        Author: PV
    '''

    def __init__(self, binderlen, weight=1, min_dist=15):

        self.binderlen = binderlen
        self.min_dist  = min_dist
        self.weight    = weight

    def compute(self, xyz):

        # Only look at monomer 1 residues
        Ca_m1 = xyz[:self.binderlen,1] # [Lb,3]
        
        # Only look at monomer 2 residues
        Ca_m2 = xyz[self.binderlen:,1] # [Lb,3]

        centroid_m1 = torch.mean(Ca_m1, dim=0, keepdim=True) # [1,3]
        centroid_m2 = torch.mean(Ca_m1, dim=0, keepdim=True) # [1,3]

        # cdist needs a batch dimension - NRB
        #This calculates RoG for Monomer 1
        dgram_m1 = torch.cdist(Ca_m1[None,...].contiguous(), centroid_m1[None,...].contiguous(), p=2) # [1,Lb,1,3]
        dgram_m1 = torch.maximum(self.min_dist * torch.ones_like(dgram_m1.squeeze(0)), dgram_m1.squeeze(0)) # [Lb,1,3]
        rad_of_gyration_m1 = torch.sqrt( torch.sum(torch.square(dgram_m1)) / Ca_m1.shape[0] ) # [1]

        # cdist needs a batch dimension - NRB
        #This calculates RoG for Monomer 2
        dgram_m2 = torch.cdist(Ca_m2[None,...].contiguous(), centroid_m2[None,...].contiguous(), p=2) # [1,Lb,1,3]
        dgram_m2 = torch.maximum(self.min_dist * torch.ones_like(dgram_m2.squeeze(0)), dgram_m2.squeeze(0)) # [Lb,1,3]
        rad_of_gyration_m2 = torch.sqrt( torch.sum(torch.square(dgram_m2)) / Ca_m2.shape[0] ) # [1]

        #Potential value is the average of both radii of gyration (is avg. the best way to do this?)
        return -1 * self.weight * (rad_of_gyration_m1 + rad_of_gyration_m2)/2

class binder_ncontacts(Potential):
    '''
        Differentiable way to maximise number of contacts within a protein
        
        Motivation is given here: https://www.plumed.org/doc-v2.7/user-doc/html/_c_o_o_r_d_i_n_a_t_i_o_n.html

    '''

    def __init__(self, binderlen, weight=1, r_0=8, d_0=4):

        self.binderlen = binderlen
        self.r_0       = r_0
        self.weight    = weight
        self.d_0       = d_0

    def compute(self, xyz):

        # Only look at binder Ca residues
        Ca = xyz[:self.binderlen,1] # [Lb,3]
        
        #cdist needs a batch dimension - NRB
        dgram = torch.cdist(Ca[None,...].contiguous(), Ca[None,...].contiguous(), p=2) # [1,Lb,Lb]
        divide_by_r_0 = (dgram - self.d_0) / self.r_0
        numerator = torch.pow(divide_by_r_0,6)
        denominator = torch.pow(divide_by_r_0,12)
        binder_ncontacts = (1 - numerator) / (1 - denominator)
        
        print("BINDER CONTACTS:", binder_ncontacts.sum())
        #Potential value is the average of both radii of gyration (is avg. the best way to do this?)
        return self.weight * binder_ncontacts.sum()

    
class dimer_ncontacts(Potential):

    '''
        Differentiable way to maximise number of contacts for two individual monomers in a dimer
        
        Motivation is given here: https://www.plumed.org/doc-v2.7/user-doc/html/_c_o_o_r_d_i_n_a_t_i_o_n.html

        Author: PV
    '''


    def __init__(self, binderlen, weight=1, r_0=8, d_0=4):

        self.binderlen = binderlen
        self.r_0       = r_0
        self.weight    = weight
        self.d_0       = d_0

    def compute(self, xyz):

        # Only look at binder Ca residues
        Ca = xyz[:self.binderlen,1] # [Lb,3]
        #cdist needs a batch dimension - NRB
        dgram = torch.cdist(Ca[None,...].contiguous(), Ca[None,...].contiguous(), p=2) # [1,Lb,Lb]
        divide_by_r_0 = (dgram - self.d_0) / self.r_0
        numerator = torch.pow(divide_by_r_0,6)
        denominator = torch.pow(divide_by_r_0,12)
        binder_ncontacts = (1 - numerator) / (1 - denominator)
        #Potential is the sum of values in the tensor
        binder_ncontacts = binder_ncontacts.sum()

        # Only look at target Ca residues
        Ca = xyz[self.binderlen:,1] # [Lb,3]
        dgram = torch.cdist(Ca[None,...].contiguous(), Ca[None,...].contiguous(), p=2) # [1,Lb,Lb]
        divide_by_r_0 = (dgram - self.d_0) / self.r_0
        numerator = torch.pow(divide_by_r_0,6)
        denominator = torch.pow(divide_by_r_0,12)
        target_ncontacts = (1 - numerator) / (1 - denominator)
        #Potential is the sum of values in the tensor
        target_ncontacts = target_ncontacts.sum()
        
        print("DIMER NCONTACTS:", (binder_ncontacts+target_ncontacts)/2)
        #Returns average of n contacts withiin monomer 1 and monomer 2
        return self.weight * (binder_ncontacts+target_ncontacts)/2

class interface_ncontacts(Potential):

    '''
        Differentiable way to maximise number of contacts between binder and target
        
        Motivation is given here: https://www.plumed.org/doc-v2.7/user-doc/html/_c_o_o_r_d_i_n_a_t_i_o_n.html

        Author: PV
    '''


    def __init__(self, binderlen, weight=1, r_0=8, d_0=6):

        self.binderlen = binderlen
        self.r_0       = r_0
        self.weight    = weight
        self.d_0       = d_0

    def compute(self, xyz):

        # Extract binder Ca residues
        Ca_b = xyz[:self.binderlen,1] # [Lb,3]

        # Extract target Ca residues
        Ca_t = xyz[self.binderlen:,1] # [Lt,3]

        #cdist needs a batch dimension - NRB
        dgram = torch.cdist(Ca_b[None,...].contiguous(), Ca_t[None,...].contiguous(), p=2) # [1,Lb,Lt]
        divide_by_r_0 = (dgram - self.d_0) / self.r_0
        numerator = torch.pow(divide_by_r_0,6)
        denominator = torch.pow(divide_by_r_0,12)
        interface_ncontacts = (1 - numerator) / (1 - denominator)
        #Potential is the sum of values in the tensor
        interface_ncontacts = interface_ncontacts.sum()

        print("INTERFACE CONTACTS:", interface_ncontacts.sum())

        return self.weight * interface_ncontacts


class monomer_contacts(Potential):
    '''
        Differentiable way to maximise number of contacts within a protein

        Motivation is given here: https://www.plumed.org/doc-v2.7/user-doc/html/_c_o_o_r_d_i_n_a_t_i_o_n.html
        Author: PV

        NOTE: This function sometimes produces NaN's -- added check in reverse diffusion for nan grads
    '''

    def __init__(self, weight=1, r_0=8, d_0=2, eps=1e-6):

        self.r_0       = r_0
        self.weight    = weight
        self.d_0       = d_0
        self.eps       = eps

    def compute(self, xyz):

        Ca = xyz[:,1] # [L,3]

        #cdist needs a batch dimension - NRB
        dgram = torch.cdist(Ca[None,...].contiguous(), Ca[None,...].contiguous(), p=2) # [1,Lb,Lb]
        divide_by_r_0 = (dgram - self.d_0) / self.r_0
        numerator = torch.pow(divide_by_r_0,6)
        denominator = torch.pow(divide_by_r_0,12)

        ncontacts = (1 - numerator) / ((1 - denominator))


        #Potential value is the average of both radii of gyration (is avg. the best way to do this?)
        return self.weight * ncontacts.sum()


def make_contact_matrix(nchain, contact_string=None):
    """
    Calculate a matrix of inter/intra chain contact indicators
    
    Parameters:
        nchain (int, required): How many chains are in this design 
        
        contact_str (str, optional): String denoting how to define contacts, comma delimited between pairs of chains
            '!' denotes repulsive, '&' denotes attractive
    """
    alphabet   = [a for a in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ']
    letter2num = {a:i for i,a in enumerate(alphabet)}
    
    contacts   = np.zeros((nchain,nchain))
    written    = np.zeros((nchain,nchain))
    
    contact_list = contact_string.split(',') 
    for c in contact_list:
        if not len(c) == 3:
            raise SyntaxError('Invalid contact(s) specification')

        i,j = letter2num[c[0]],letter2num[c[2]]
        symbol = c[1]
        
        # denote contacting/repulsive
        assert symbol in ['!','&']
        if symbol == '!':
            contacts[i,j] = -1
            contacts[j,i] = -1
        else:
            contacts[i,j] = 1
            contacts[j,i] = 1
            
    return contacts 


class olig_contacts(Potential):
    """
    Applies PV's num contacts potential within/between chains in symmetric oligomers 

    Author: DJ 
    """

    def __init__(self, 
                 contact_matrix, 
                 weight_intra=1, 
                 weight_inter=1,
                 r_0=8, d_0=2):
        """
        Parameters:
            chain_lengths (list, required): List of chain lengths, length is (Nchains)

            contact_matrix (torch.tensor/np.array, required): 
                square matrix of shape (Nchains,Nchains) whose (i,j) enry represents 
                attractive (1), repulsive (-1), or non-existent (0) contact potentials 
                between chains in the complex

            weight (int/float, optional): Scaling/weighting factor
        """
        self.contact_matrix = contact_matrix
        self.weight_intra = weight_intra 
        self.weight_inter = weight_inter 
        self.r_0 = r_0
        self.d_0 = d_0

        # check contact matrix only contains valid entries 
        assert all([i in [-1,0,1] for i in contact_matrix.flatten()]), 'Contact matrix must contain only 0, 1, or -1 in entries'
        # assert the matrix is square and symmetric 
        shape = contact_matrix.shape 
        assert len(shape) == 2 
        assert shape[0] == shape[1]
        for i in range(shape[0]):
            for j in range(shape[1]):
                assert contact_matrix[i,j] == contact_matrix[j,i]
        self.nchain=shape[0]

         
    #   self._compute_chain_indices()

    # def _compute_chain_indices(self):
    #     # make list of shape [i,N] for indices of each chain in total length
    #     indices = []
    #     start   = 0
    #     for l in self.chain_lengths:
    #         indices.append(torch.arange(start,start+l))
    #         start += l
    #     self.indices = indices 

    def _get_idx(self,i,L):
        """
        Returns the zero-indexed indices of the residues in chain i
        """
        assert L%self.nchain == 0
        Lchain = L//self.nchain
        return i*Lchain + torch.arange(Lchain)


    def compute(self, xyz):
        """
        Iterate through the contact matrix, compute contact potentials between chains that need it,
        and negate contacts for any 
        """
        L = xyz.shape[0]

        all_contacts = 0
        start = 0
        for i in range(self.nchain):
            for j in range(self.nchain):
                # only compute for upper triangle, disregard zeros in contact matrix 
                if (i <= j) and (self.contact_matrix[i,j] != 0):

                    # get the indices for these two chains 
                    idx_i = self._get_idx(i,L)
                    idx_j = self._get_idx(j,L)

                    Ca_i = xyz[idx_i,1]  # slice out crds for this chain 
                    Ca_j = xyz[idx_j,1]  # slice out crds for that chain 
                    dgram           = torch.cdist(Ca_i[None,...].contiguous(), Ca_j[None,...].contiguous(), p=2) # [1,Lb,Lb]

                    divide_by_r_0   = (dgram - self.d_0) / self.r_0
                    numerator       = torch.pow(divide_by_r_0,6)
                    denominator     = torch.pow(divide_by_r_0,12)
                    ncontacts       = (1 - numerator) / (1 - denominator)

                    # weight, don't double count intra 
                    scalar = (i==j)*self.weight_intra/2 + (i!=j)*self.weight_inter

                    #                 contacts              attr/repuls          relative weights 
                    all_contacts += ncontacts.sum() * self.contact_matrix[i,j] * scalar 

        return all_contacts 
                    

class olig_intra_contacts(Potential):
    """
    Applies PV's num contacts potential for each chain individually in an oligomer design 

    Author: DJ 
    """

    def __init__(self, chain_lengths, weight=1):
        """
        Parameters:

            chain_lengths (list, required): Ordered list of chain lengths 

            weight (int/float, optional): Scaling/weighting factor
        """
        self.chain_lengths = chain_lengths 
        self.weight = weight 


    def compute(self, xyz):
        """
        Computes intra-chain num contacts potential
        """
        assert sum(self.chain_lengths) == xyz.shape[0], 'given chain lengths do not match total protein length'

        all_contacts = 0
        start = 0
        for Lc in self.chain_lengths:
            Ca = xyz[start:start+Lc]  # slice out crds for this chain 
            dgram = torch.cdist(Ca[None,...].contiguous(), Ca[None,...].contiguous(), p=2) # [1,Lb,Lb]
            divide_by_r_0 = (dgram - self.d_0) / self.r_0
            numerator = torch.pow(divide_by_r_0,6)
            denominator = torch.pow(divide_by_r_0,12)
            ncontacts = (1 - numerator) / (1 - denominator)

            # add contacts for this chain to all contacts 
            all_contacts += ncontacts.sum()

            # increment the start to be at the next chain 
            start += Lc 


        return self.weight * all_contacts

def get_damped_lj(r_min, r_lin,p1=6,p2=12):
    
    y_at_r_lin = lj(r_lin, r_min, p1, p2)
    ydot_at_r_lin = lj_grad(r_lin, r_min,p1,p2)
    
    def inner(dgram):
        return (dgram < r_lin) * (ydot_at_r_lin * (dgram - r_lin) + y_at_r_lin) + (dgram >= r_lin) * lj(dgram, r_min, p1, p2)
    return inner

def lj(dgram, r_min,p1=6, p2=12):
    return 4 * ((r_min / (2**(1/p1) * dgram))**p2 - (r_min / (2**(1/p1) * dgram))**p1)

def lj_grad(dgram, r_min,p1=6,p2=12):
    return -p2 * r_min**p1*(r_min**p1-dgram**p1) / (dgram**(p2+1))

def mask_expand(mask, n=1):
    mask_out = mask.clone()
    assert mask.ndim == 1
    for i in torch.where(mask)[0]:
        for j in range(i-n, i+n+1):
            if j >= 0 and j < len(mask):
                mask_out[j] = True
    return mask_out

def contact_energy(dgram, d_0, r_0):
    divide_by_r_0 = (dgram - d_0) / r_0
    numerator = torch.pow(divide_by_r_0,6)
    denominator = torch.pow(divide_by_r_0,12)
    
    ncontacts = (1 - numerator) / ((1 - denominator)).float()
    return - ncontacts

def poly_repulse(dgram, r, slope, p=1):
    a = slope / (p * r**(p-1))

    return (dgram < r) * a * torch.abs(r - dgram)**p * slope

#def only_top_n(dgram


class substrate_contacts(Potential):
    '''
    Implicitly models a ligand with an attractive-repulsive potential.
    '''

    def __init__(self, weight=1, r_0=8, d_0=2, s=1, eps=1e-6, rep_r_0=5, rep_s=2, rep_r_min=1):

        self.r_0       = r_0
        self.weight    = weight
        self.d_0       = d_0
        self.eps       = eps
        
        # motif frame coordinates
        # NOTE: these probably need to be set after sample_init() call, because the motif sequence position in design must be known
        self.motif_frame = None # [4,3] xyz coordinates from 4 atoms of input motif
        self.motif_mapping = None # list of tuples giving positions of above atoms in design [(resi, atom_idx)]
        self.motif_substrate_atoms = None # xyz coordinates of substrate from input motif
        r_min = 2
        self.energies = []
        self.energies.append(lambda dgram: s * contact_energy(torch.min(dgram, dim=-1)[0], d_0, r_0))
        if rep_r_min:
            self.energies.append(lambda dgram: poly_repulse(torch.min(dgram, dim=-1)[0], rep_r_0, rep_s, p=1.5))
        else:
            self.energies.append(lambda dgram: poly_repulse(dgram, rep_r_0, rep_s, p=1.5))


    def compute(self, xyz):
        
        # First, get random set of atoms
        # This operates on self.xyz_motif, which is assigned to this class in the model runner (for horrible plumbing reasons)
        self._grab_motif_residues(self.xyz_motif)
        
        # for checking affine transformation is corect
        first_distance = torch.sqrt(torch.sqrt(torch.sum(torch.square(self.motif_substrate_atoms[0] - self.motif_frame[0]), dim=-1))) 

        # grab the coordinates of the corresponding atoms in the new frame using mapping
        res = torch.tensor([k[0] for k in self.motif_mapping])
        atoms = torch.tensor([k[1] for k in self.motif_mapping])
        new_frame = xyz[self.diffusion_mask][res,atoms,:]
        # calculate affine transformation matrix and translation vector b/w new frame and motif frame
        A, t = self._recover_affine(self.motif_frame, new_frame)
        # apply affine transformation to substrate atoms
        substrate_atoms = torch.mm(A, self.motif_substrate_atoms.transpose(0,1)).transpose(0,1) + t
        second_distance = torch.sqrt(torch.sqrt(torch.sum(torch.square(new_frame[0] - substrate_atoms[0]), dim=-1)))
        assert abs(first_distance - second_distance) < 0.01, "Alignment seems to be bad" 
        diffusion_mask = mask_expand(self.diffusion_mask, 1)
        Ca = xyz[~diffusion_mask, 1]

        #cdist needs a batch dimension - NRB
        dgram = torch.cdist(Ca[None,...].contiguous(), substrate_atoms.float()[None], p=2)[0] # [Lb,Lb]

        all_energies = []
        for i, energy_fn in enumerate(self.energies):
            energy = energy_fn(dgram)
            all_energies.append(energy.sum())
        return - self.weight * sum(all_energies)

        #Potential value is the average of both radii of gyration (is avg. the best way to do this?)
        return self.weight * ncontacts.sum()

    def _recover_affine(self,frame1, frame2):
        """
        Uses Simplex Affine Matrix (SAM) formula to recover affine transform between two sets of 4 xyz coordinates
        See: https://www.researchgate.net/publication/332410209_Beginner%27s_guide_to_mapping_simplexes_affinely

        Args: 
        frame1 - 4 coordinates from starting frame [4,3]
        frame2 - 4 coordinates from ending frame [4,3]
        
        Outputs:
        A - affine transformation matrix from frame1->frame2
        t - affine translation vector from frame1->frame2
        """

        l = len(frame1)
        # construct SAM denominator matrix
        B = torch.vstack([frame1.T, torch.ones(l)])
        D = 1.0 / torch.linalg.det(B) # SAM denominator

        M = torch.zeros((3,4), dtype=torch.float64)
        for i, R in enumerate(frame2.T):
            for j in range(l):
                num = torch.vstack([R, B])
                # make SAM numerator matrix
                num = torch.cat((num[:j+1],num[j+2:])) # make numerator matrix
                # calculate SAM entry
                M[i][j] = (-1)**j * D * torch.linalg.det(num)

        A, t = torch.hsplit(M, [l-1])
        t = t.transpose(0,1)
        return A, t

    def _grab_motif_residues(self, xyz) -> None:
        """
        Grabs 4 atoms in the motif.
        Currently random subset of Ca atoms if the motif is >= 4 residues, or else 4 random atoms from a single residue
        """
        idx = torch.arange(self.diffusion_mask.shape[0])
        idx = idx[self.diffusion_mask].float()
        if torch.sum(self.diffusion_mask) >= 4:
            rand_idx = torch.multinomial(idx, 4).long()
            # get Ca atoms
            self.motif_frame = xyz[rand_idx, 1]
            self.motif_mapping = [(i,1) for i in rand_idx]
        else:
            rand_idx = torch.multinomial(idx, 1).long()
            self.motif_frame = xyz[rand_idx[0],:4]
            self.motif_mapping = [(rand_idx, i) for i in range(4)]

class binder_distance_ReLU(Potential):
    '''
        Given the current coordinates of the diffusion trajectory, calculate a potential that is the distance between each residue
        and the closest target residue.

        This potential is meant to encourage the binder to interact with a certain subset of residues on the target that 
        define the binding site.

        Author: NRB
    '''

    def __init__(self, binderlen, hotspot_res, weight=1, min_dist=15, use_Cb=False):

        self.binderlen   = binderlen
        self.hotspot_res = [res + binderlen for res in hotspot_res]
        self.weight      = weight
        self.min_dist    = min_dist
        self.use_Cb      = use_Cb

    def compute(self, xyz):
        binder = xyz[:self.binderlen,:,:] # (Lb,27,3)
        target = xyz[self.hotspot_res,:,:] # (N,27,3)

        if self.use_Cb:
            N  = binder[:,0]
            Ca = binder[:,1]
            C  = binder[:,2]

            Cb = generate_Cbeta(N,Ca,C) # (Lb,3)

            N_t  = target[:,0]
            Ca_t = target[:,1]
            C_t  = target[:,2]

            Cb_t = generate_Cbeta(N_t,Ca_t,C_t) # (N,3)

            dgram = torch.cdist(Cb[None,...], Cb_t[None,...], p=2) # (1,Lb,N)

        else:
            # Use Ca dist for potential

            Ca = binder[:,1] # (Lb,3)

            Ca_t = target[:,1] # (N,3)

            dgram = torch.cdist(Ca[None,...], Ca_t[None,...], p=2) # (1,Lb,N)

        closest_dist = torch.min(dgram.squeeze(0), dim=1)[0] # (Lb)

        # Cap the distance at a minimum value
        min_distance = self.min_dist * torch.ones_like(closest_dist) # (Lb)
        potential    = torch.maximum(min_distance, closest_dist) # (Lb)

        # torch.Tensor.backward() requires the potential to be a single value
        potential    = torch.sum(potential, dim=-1)
        
        return -1 * self.weight * potential

class binder_any_ReLU(Potential):
    '''
        Given the current coordinates of the diffusion trajectory, calculate a potential that is the minimum distance between
        ANY residue and the closest target residue.

        In contrast to binder_distance_ReLU this potential will only penalize a pose if all of the binder residues are outside
        of a certain distance from the target residues.

        Author: NRB
    '''

    def __init__(self, binderlen, hotspot_res, weight=1, min_dist=15, use_Cb=False):

        self.binderlen   = binderlen
        self.hotspot_res = [res + binderlen for res in hotspot_res]
        self.weight      = weight
        self.min_dist    = min_dist
        self.use_Cb      = use_Cb

    def compute(self, xyz):
        binder = xyz[:self.binderlen,:,:] # (Lb,27,3)
        target = xyz[self.hotspot_res,:,:] # (N,27,3)

        if use_Cb:
            N  = binder[:,0]
            Ca = binder[:,1]
            C  = binder[:,2]

            Cb = generate_Cbeta(N,Ca,C) # (Lb,3)

            N_t  = target[:,0]
            Ca_t = target[:,1]
            C_t  = target[:,2]

            Cb_t = generate_Cbeta(N_t,Ca_t,C_t) # (N,3)

            dgram = torch.cdist(Cb[None,...], Cb_t[None,...], p=2) # (1,Lb,N)

        else:
            # Use Ca dist for potential

            Ca = binder[:,1] # (Lb,3)

            Ca_t = target[:,1] # (N,3)

            dgram = torch.cdist(Ca[None,...], Ca_t[None,...], p=2) # (1,Lb,N)


        closest_dist = torch.min(dgram.squeeze(0)) # (1)

        potential    = torch.maximum(min_dist, closest_dist) # (1)

        return -1 * self.weight * potential

class cyclic_peptide_geometry(Potential):
    '''
    Potential to encourage a specific geometry for cyclic peptides.
    This potential aims to maintain a regular polygon shape with a specified number of sides.
    '''

    def __init__(self, n_residues, target_radius=5.0, weight=1.0):
        self.n_residues = n_residues
        self.target_radius = target_radius
        self.weight = weight

        # Calculate target coordinates for a regular polygon
        angles = np.linspace(0, 2*np.pi, n_residues, endpoint=False)
        self.target_coords = torch.tensor([
            [np.cos(angle) * target_radius, np.sin(angle) * target_radius, 0]
            for angle in angles
        ], dtype=torch.float32)

    def compute(self, xyz):
        # Extract CA coordinates
        Ca = xyz[:self.n_residues, 1]  # [n_residues, 3]

        # Calculate centroid
        centroid = torch.mean(Ca, dim=0, keepdim=True)  # [1, 3]

        # Center the coordinates
        centered_coords = Ca - centroid

        # Calculate the current radius for each residue
        current_radii = torch.norm(centered_coords, dim=1)

        # Calculate the angular positions of the current coordinates
        current_angles = torch.atan2(centered_coords[:, 1], centered_coords[:, 0])

        # Sort the current angles and get the sorting indices
        sorted_indices = torch.argsort(current_angles)

        # Reorder the centered coordinates based on the sorted angles
        ordered_coords = centered_coords[sorted_indices]

        # Calculate the distance between the current and target coordinates
        distance = torch.norm(ordered_coords - self.target_coords, dim=1)

        # Calculate the potential as the mean squared distance
        potential = torch.mean(distance**2)

        # Add a term to encourage uniform spacing between residues
        angle_diffs = torch.diff(current_angles[sorted_indices], append=current_angles[sorted_indices[:1]] + 2*np.pi)
        angle_uniformity = torch.var(angle_diffs)

        # Combine the distance and angle uniformity terms
        combined_potential = potential + angle_uniformity

        # Return the negative potential (to be maximized)
        return -self.weight * combined_potential

# Dictionary of types of potentials indexed by name of potential. Used by PotentialManager.
# If you implement a new potential you must add it to this dictionary for it to be used by
# the PotentialManager
implemented_potentials = { 'monomer_ROG':          monomer_ROG,
                           'binder_ROG':           binder_ROG,
                           'binder_distance_ReLU': binder_distance_ReLU,
                           'binder_any_ReLU':      binder_any_ReLU,
                           'dimer_ROG':            dimer_ROG,
                           'binder_ncontacts':     binder_ncontacts,
                           'dimer_ncontacts':      dimer_ncontacts,
                           'interface_ncontacts':  interface_ncontacts,
                           'monomer_contacts':     monomer_contacts,
                           'olig_intra_contacts':  olig_intra_contacts,
                           'olig_contacts':        olig_contacts,
                           'substrate_contacts':    substrate_contacts}

# Add the new potential to the implemented_potentials dictionary
implemented_potentials['cyclic_peptide_geometry'] = cyclic_peptide_geometry

require_binderlen      = { 'binder_ROG',
                           'binder_distance_ReLU',
                           'binder_any_ReLU',
                           'dimer_ROG',
                           'binder_ncontacts',
                           'dimer_ncontacts',
                           'interface_ncontacts'}

require_hotspot_res    = { 'binder_distance_ReLU',
                           'binder_any_ReLU' }

