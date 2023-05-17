import os
import copy
import PIL
import torch
import torchvision
import numpy as np
import math

import logging
from typing import List

LOG = logging.getLogger(__name__)

def flip_image_and_bbox(img, anns):
    img = img.transpose(PIL.Image.FLIP_LEFT_RIGHT)
    w, _ = img.size
    x_max = w - anns['bbox'][0]
    x_min = w - anns['bbox'][2]
    anns['bbox'][0] = x_min
    anns['bbox'][2] = x_max
    return img


def define_path(use_jaad=True, use_pie=True, use_titan=True):
    """
    Define default path to data
    """
    # Uncomment it when running on SCITAS
    # SCITAS:
    # anns:/work/scitas-share/datasets/Vita/civil-459/JAAD/data_cache/jaad_database.pkl
    # split:DATA/annotations/JAAD/splits/
    # image JAAD:/work/scitas-share/datasets/Vita/civil-459/JAAD/images
    all_anns_paths = {'JAAD': {'anns': '/work/scitas-share/datasets/Vita/civil-459/JAAD/data_cache/jaad_database.pkl',
                               'split': 'DATA/annotations/JAAD/splits/'},
                      'PIE': {'anns': 'TransNet/DATA/PIE_DATA.pkl'},
                      'TITAN': {'anns': '/work/vita/datasets/TITAN/titan_0_4/',
                                'split': '/work/vita/datasets/TITAN/splits/'}
                      }
    # change from JAAD images: '/work/vita/datasets/JAAD/images/' to 'D:\VisualStudioProgram\JAAD-JAAD_2.0\JAAD-JAAD_2.0\images'
    all_image_dir = {'JAAD': '/work/scitas-share/datasets/Vita/civil-459/JAAD/images',
                     'PIE': '/work/vita/datasets/PIE/images/',
                     'TITAN': '/work/vita/datasets/TITAN/images_anonymized/'
                     }
    
    # Uncomment it when running on Jessica's computer
    # change from JAAD anns: 'TransNet/DATA/JAAD_DATA.pkl' to 'DATA/annotations/JAAD/anns/JAAD_DATA.pkl'
    # change from JAAD split: '/work/vita/datasets/JAAD/split_ids/' to 'DATA/annotations/JAAD/splits'
    # all_anns_paths = {'JAAD': {'anns': 'DATA/annotations/JAAD/anns/JAAD_DATA.pkl',
    #                            'split': 'DATA/annotations/JAAD/splits'},
    #                   'PIE': {'anns': 'TransNet/DATA/PIE_DATA.pkl'},
    #                   'TITAN': {'anns': '/work/vita/datasets/TITAN/titan_0_4/',
    #                             'split': '/work/vita/datasets/TITAN/splits/'}
    #                   }
    # # change from JAAD images: '/work/vita/datasets/JAAD/images/' to 'D:\VisualStudioProgram\JAAD-JAAD_2.0\JAAD-JAAD_2.0\images'
    # all_image_dir = {'JAAD': 'D:\VisualStudioProgram\JAAD-JAAD_2.0\JAAD-JAAD_2.0\images',
    #                  'PIE': '/work/vita/datasets/PIE/images/',
    #                  'TITAN': '/work/vita/datasets/TITAN/images_anonymized/'
    #                  }

    # Uncomment it when running on Arina's computer
    # change from JAAD anns: 'TransNet/DATA/JAAD_DATA.pkl' to 'DATA/annotations/JAAD/anns/JAAD_DATA.pkl'
    # change from JAAD split: '/work/vita/datasets/JAAD/split_ids/' to 'DATA/annotations/JAAD/splits'
    #all_anns_paths = {'JAAD': {'anns': 'DATA/annotations/JAAD/anns/JAAD_DATA.pkl',
    #                            'split': 'DATA/annotations/JAAD/splits'},
    #                   'PIE': {'anns': 'TransNet/DATA/PIE_DATA.pkl'},
    #                   'TITAN': {'anns': '/work/vita/datasets/TITAN/titan_0_4/',
    #                            'split': '/work/vita/datasets/TITAN/splits/'}
    #                   }

    #all_image_dir = {'JAAD': 'D:\VisualStudioProgram\JAAD-JAAD_2.0\JAAD-JAAD_2.0\images',
    #                  'PIE': '/work/vita/datasets/PIE/images/',
    #                  'TITAN': '/work/vita/datasets/TITAN/images_anonymized/'
    #                  }
    anns_paths = {}
    image_dir = {}
    if use_jaad:
        anns_paths['JAAD'] = all_anns_paths['JAAD']
        image_dir['JAAD'] = all_image_dir['JAAD']
    if use_pie:
        anns_paths['PIE'] = all_anns_paths['PIE']
        image_dir['PIE'] = all_image_dir['PIE']
    if use_titan:
        anns_paths['TITAN'] = all_anns_paths['TITAN']
        image_dir['TITAN'] = all_image_dir['TITAN']

    return anns_paths, image_dir
    

class ImageList(torch.utils.data.Dataset):
    """
    Basic dataloader for images
    """

    def __init__(self, image_paths, preprocess=None):
        self.image_paths = image_paths
        self.preprocess = preprocess

    def __getitem__(self, index):
        image_path = self.image_paths[index]
        with open(image_path, 'rb') as f:
            image = PIL.Image.open(f).convert('RGB')
        if self.preprocess is not None:
            image = self.preprocess(image)

        return image

    def __len__(self):
        return len(self.image_paths)


class MultiLoader:
    # loading data from mulitple datasets
    last_task_index = None
    

    def __init__(self, loaders: List[torch.utils.data.DataLoader], 
                 weights=None,  n_batches=None):
                 
        self.loaders = loaders
        self._weights = weights

        if self._weights is None:
            self._weights = [1.0 / len(loaders) for _ in range(len(loaders))]
        elif len(self._weights) == len(loaders) - 1:
            self._weights.append(1.0 - sum(self._weights))
        elif len(self._weights) == len(loaders):
            pass
        else:
            raise Exception('invalid dataset weights: {}'.format(self._weights))
        assert all(w > 0.0 for w in self._weights)
        sum_w = sum(self._weights)
        # normalize weights between datasets
        self._weights = [w / sum_w for w in self._weights]
        LOG.info('dataset weights: %s', self._weights)
        # set the total number of batches in one epoch
        self.n_batches = int(min(len(l) / w for l, w in zip(loaders, self._weights)))
        if n_batches is not None:
            self.n_batches = min(self.n_batches, n_batches)

    def __iter__(self):
        loader_iters = [iter(l) for l in self.loaders]
        # counter of loaded batches for each dataset
        n_loaded = [0 for _ in self.loaders]
        while True:
            # select loader for one iteration
            loader_index = int(np.argmin([n / w for n, w in zip(n_loaded, self._weights)]))
            next_batch = next(loader_iters[loader_index], None)
            if next_batch is None:
                break
            n_loaded[loader_index] += 1
            MultiLoader.last_task_index = loader_index
            # generator
            yield next_batch
            # termination
            if sum(n_loaded) >= self.n_batches:
                break

    def __len__(self):
        return self.n_batches
        

class FrameDataset(torch.utils.data.Dataset):

    def __init__(self, samples, image_dir, preprocess=None):
        self.samples = samples
        self.image_dir = image_dir
        self.preprocess = preprocess

    def __getitem__(self, index):
        ids = list(self.samples.keys())
        idx = ids[index]
        frame = self.samples[idx]['frame']
        bbox = copy.deepcopy(self.samples[idx]['bbox'])
        source = self.samples[idx]["source"]
        anns = {'bbox': bbox, 'source': source}
        TTE = self.samples[idx]["TTE"]
        if 'trans_label' in list(self.samples[idx].keys()):
            label = self.samples[idx]['trans_label']
        else:
            label = None
        if 'behavior' in list(self.samples[idx].keys()):
            behavior = self.samples[idx]['behavior']
        else:
            behavior = [-1,-1,-1,-1] # no behavior annotations
        if 'attributes' in list(self.samples[idx].keys()):
            attributes = self.samples[idx]['attributes'] # scene attributes
        else:
            attributes = [-1,-1,-1,-1,-1,-1]
        image_path = None
        # image paths
        if source == "JAAD":
            vid = self.samples[idx]['video_number']
            image_path = os.path.join(self.image_dir['JAAD'], vid, '{:05d}.png'.format(frame))
        elif source == "PIE":
            vid = self.samples[idx]['video_number']
            sid = self.samples[idx]['set_number']
            image_path = os.path.join(self.image_dir['PIE'], sid, vid, '{:05d}.png'.format(frame))
        elif source == "TITAN":
            vid = self.samples[idx]['video_number']
            image_path = os.path.join(self.image_dir['TITAN'], vid, 'images', '{:06}.png'.format(frame))

        with open(image_path, 'rb') as f:
            img = PIL.Image.open(f).convert('RGB')
        if self.preprocess is not None:
            img, anns = self.preprocess(img, anns)
        img_tensor = torchvision.transforms.ToTensor()(img)
        if label is not None:
            label = torch.tensor(label)
            label = label.to(torch.float32)
            
        if math.isnan(TTE):
            pass
        else:
            TTE = round(self.samples[idx]["TTE"],2)
        TTE = torch.tensor(TTE).to(torch.float32)
        attributes = torch.tensor(attributes).to(torch.float32)
        sample = {'image': img_tensor, 'bbox': anns['bbox'], 'id': idx,
                   'label': label, 'source': source, 'TTE': TTE,
                   'attributes': attributes, 'behavior': behavior
                   }

        return sample

    def __len__(self):
        return len(self.samples.keys())


class SimpleSequenceDataset(torch.utils.data.Dataset):
    """
    Basic dataloader for loading sequence/history samples
    """

    def __init__(self, samples, image_dir, preprocess=None):
        """
        :params: samples: transition history samples(dict)
                image_dir: root dir for images extracted from video clips
                preprocess: optional preprocessing on image tensors and annotations
        """
        self.samples = samples
        self.image_dir = image_dir
        self.preprocess = preprocess

    def __getitem__(self, index):
        ids = list(self.samples.keys())
        idx = ids[index]
        frames = self.samples[idx]['frame']
        bbox = copy.deepcopy(self.samples[idx]['bbox'])
        source = self.samples[idx]["source"]
        bbox_new= []
        image_path = None
        # image paths
        img_tensors = []
        for i in range(len(frames)):
            anns = {'bbox': bbox[i], 'source': source}
            if source == "JAAD":
                vid = self.samples[idx]['video_number']
                image_path = os.path.join(self.image_dir['JAAD'], vid, '{:05d}.png'.format(frames[i]))
            elif source == "PIE":
                vid = self.samples[idx]['video_number']
                sid = self.samples[idx]['set_number']
                image_path = os.path.join(self.image_dir['PIE'], sid, vid, '{:05d}.png'.format(frames[i]))
            elif source == "TITAN":
                vid = self.samples[idx]['video_number']
                image_path = os.path.join(self.image_dir['TITAN'], vid, 'images', '{:06}.png'.format(frames[i]))
            with open(image_path, 'rb') as f:
                img = PIL.Image.open(f).convert('RGB')
            if self.preprocess is not None:
                img, anns = self.preprocess(img, anns)
            img_tensors.append(torchvision.transforms.ToTensor()(img))
            bbox_new.append(anns['bbox'])
        img_tensors = torch.stack(img_tensors)
        sample = {'image': img_tensors, 'bbox': bbox_new, 'id': idx,  'source': source}

        return sample

    def __len__(self):
        return len(self.samples.keys())
        

class SequenceDataset(torch.utils.data.Dataset):
    """
    Basic dataloader for loading sequence/history samples
    """

    def __init__(self, samples, image_dir, preprocess=None):
        """
        :params: samples: transition history samples(dict)
                image_dir: root dir for images extracted from video clips
                preprocess: optional preprocessing on image tensors and annotations
        """
        self.samples = samples
        self.image_dir = image_dir
        self.preprocess = preprocess

    def __getitem__(self, index):
        ids = list(self.samples.keys())
        idx = ids[index]
        frames = self.samples[idx]['frame']
        bbox = copy.deepcopy(self.samples[idx]['bbox'])
        source = self.samples[idx]["source"]
        action = self.samples[idx]['action']
        TTE = round(self.samples[idx]["TTE"],2)
        if 'trans_label' in list(self.samples[idx].keys()):
            label = self.samples[idx]['trans_label']
        else:
            label = None
        bbox_new= []
        image_path = None
        # image paths
        img_tensors = []
        for i in range(len(frames)):
            anns = {'bbox': bbox[i], 'source': source}
            if source == "JAAD":
                vid = self.samples[idx]['video_number']
                image_path = os.path.join(self.image_dir['JAAD'], vid, '{:05d}.png'.format(frames[i]))
            elif source == "PIE":
                vid = self.samples[idx]['video_number']
                sid = self.samples[idx]['set_number']
                image_path = os.path.join(self.image_dir['PIE'], sid, vid, '{:05d}.png'.format(frames[i]))
            elif source == "TITAN":
                vid = self.samples[idx]['video_number']
                image_path = os.path.join(self.image_dir['TITAN'], vid, 'images', '{:06}.png'.format(frames[i]))
            with open(image_path, 'rb') as f:
                img = PIL.Image.open(f).convert('RGB')
            if self.preprocess is not None:
                img, anns = self.preprocess(img, anns)
            img_tensors.append(torchvision.transforms.ToTensor()(img))
            bbox_new.append(anns['bbox'])
        img_tensors = torch.stack(img_tensors)
        if label is not None:
            label = torch.tensor(label)
            label = label.to(torch.float32)
        sample = {'image': img_tensors, 'bbox': bbox_new, 'action': action, 'id': idx, 'label': label, 'source': source, 'TTE': TTE }

        return sample

    def __len__(self):
        return len(self.samples.keys())


class PaddedSequenceDataset(torch.utils.data.Dataset):
    """
    Basic dataloader for loading sequence/history samples
    """

    def __init__(self, samples, image_dir, padded_length=10, preprocess=None, hflip_p=0.0):
        """
        :params: samples: transition history samples(dict)
                image_dir: root dir for images extracted from video clips
                preprocess: optional preprocessing on image tensors and annotations
        """
        self.samples = samples
        self.image_dir = image_dir
        self.preprocess = preprocess
        self.padded_length = padded_length
        self.hflip_p = hflip_p

    def __getitem__(self, index):
        ids = list(self.samples.keys())
        idx = ids[index]
        frames = self.samples[idx]['frame']
        bbox = copy.deepcopy(self.samples[idx]['bbox'])
        source = self.samples[idx]["source"]
        action = self.samples[idx]['action']
        TTE = self.samples[idx]["TTE"]
        if source == "PIE":
           set_number = self.samples[idx]['set_number']
        else:
           set_number = None
        # trace = {"source": source, "video_number": self.samples[idx]['video_number'],
                 # "set_number": set_number, "end_frame": frames[-1], "end_bbox": bbox[-1]}
        if 'trans_label' in list(self.samples[idx].keys()):
            label = self.samples[idx]['trans_label']
        else:
            label = None
        if 'behavior' in list(self.samples[idx].keys()):
            behavior = self.samples[idx]['behavior']
        else:
            behavior = [-1,-1,-1,-1]
        if 'attributes' in list(self.samples[idx].keys()):
            attributes = self.samples[idx]['attributes']
        else:
            attributes = [-1,-1,-1,-1,-1,-1]
        """
        if 'traffic_light' in list(self.samples[idx].keys()):
            traffic_light = self.samples[idx]['traffic_light']
        else:
            traffic_light = []
        """
        bbox_new = []
        bbox_ped_new = []
        image_path = None
        # image paths
        img_tensors = []
        hflip = True if float(torch.rand(1).item()) < self.hflip_p else False
        for i in range(len(frames)):
            # bbox_ped = copy.deepcopy(bbox[i])
            anns = {'bbox': bbox[i], 'source': source}
            if source == "JAAD":
                vid = self.samples[idx]['video_number']
                image_path = os.path.join(self.image_dir['JAAD'], vid, '{:05d}.png'.format(frames[i]))
            elif source == "PIE":
                vid = self.samples[idx]['video_number']
                sid = self.samples[idx]['set_number']
                image_path = os.path.join(self.image_dir['PIE'], sid, vid, '{:05d}.png'.format(frames[i]))
            elif source == "TITAN":
                vid = self.samples[idx]['video_number']
                image_path = os.path.join(self.image_dir['TITAN'], vid, 'images', '{:06}.png'.format(frames[i]))
            with open(image_path, 'rb') as f:
                img = PIL.Image.open(f).convert('RGB')
            if hflip:
                img = img.transpose(PIL.Image.FLIP_LEFT_RIGHT)
                w, h = img.size
                x_max = w - anns['bbox'][0]
                x_min = w - anns['bbox'][2]
                anns['bbox'][0] = x_min
                anns['bbox'][2] = x_max
            anns['bbox_ped'] =  copy.deepcopy(anns['bbox'])
            if self.preprocess is not None:
                img, anns = self.preprocess(img, anns)
            img_tensors.append(torchvision.transforms.ToTensor()(img))
            bbox_new.append(anns['bbox'])
            bbox_ped_new.append(anns['bbox_ped'])
    
        img_tensors = torch.stack(img_tensors)
        imgs_size = img_tensors.size()
        img_tensors_padded = torch.zeros((self.padded_length, imgs_size[1], imgs_size[2], imgs_size[3]))
        img_tensors_padded[:imgs_size[0], :, :, :] = img_tensors
        bbox_new_padded = copy.deepcopy(bbox_new)
        bbox_ped_new_padded = copy.deepcopy(bbox_ped_new)
        action_padded = copy.deepcopy(action)
        behavior_padded = copy.deepcopy(behavior)
        # traffic_light_padded = copy.deepcopy(traffic_light)
        for i in range(imgs_size[0],self.padded_length):
            bbox_new_padded.append([0,0,0,0])
            bbox_ped_new_padded.append([0,0,0,0])
            action_padded.append(-1)
            behavior_padded.append([-1,-1,-1,-1])
            # traffic_light_padded.append(-1)
        # seq_len = torch.squeeze(torch.LongTensor(imgs_size[0]))
        seq_len = imgs_size[0]
        if label is not None:
            label = torch.tensor(label)
            label = label.to(torch.float32)
        TTE_tag = -1
        if math.isnan(TTE):
            pass
        else:
            TTE = round(self.samples[idx]["TTE"],2)
            if TTE < 0.45:
               TTE_tag = 0
            elif 0.45 < TTE < 0.85:
               TTE_tag = 1
            elif 0.85 < TTE < 1.25:
               TTE_tag = 2
            elif 1.25 < TTE < 1.65:
               TTE_tag = 3
            elif 1.65 < TTE < 2.05:
               TTE_tag = 4
            else:
               TTE_tag = 5
        TTE = torch.tensor(TTE).to(torch.float32)
        TTE_tag = torch.tensor(TTE_tag)
        TTE_tag = TTE_tag.to(torch.float32)
        attributes = torch.tensor(attributes).to(torch.float32)
        sample = {'image': img_tensors_padded, 'bbox': bbox_new_padded, 'bbox_ped': bbox_ped_new_padded,
                  'seq_length': seq_len, 'action': action_padded, 'id': idx, 'label': label,
                  'source': source, 'TTE': TTE, 'TTE_tag': TTE_tag,  
                  'behavior': behavior_padded, 'attributes': attributes}

        return sample

    def __len__(self):
        return len(self.samples.keys())
        

class IntentionSequenceDataset(torch.utils.data.Dataset):
    """
    Basic dataloader for loading sequence/history samples
    """

    def __init__(self, samples, image_dir, preprocess=None, hflip_p=0.0):
        """
        :params: samples: pedestrian trajectory samples(dict)
                image_dir: root dir for images extracted from video clips
                preprocess: optional preprocessing on image tensors and annotations
        """
        self.samples = samples
        self.image_dir = image_dir
        self.preprocess = preprocess
        self.hflip_p = hflip_p
        self._to_tensor = torchvision.transforms.ToTensor()

    def __getitem__(self, index):
        sample_id = self.samples[index]['sample_id']
        frames = self.samples[index]['frames']
        attributes = torch.tensor(self.samples[index]['attributes'])
        action = self.samples[index]['action']
        behavior = torch.tensor(self.samples[index]['behavior'], dtype=torch.float32)
        bbox = copy.deepcopy(self.samples[index]['bbox'])
        label = self.samples[index]['label']
        bbox_new = []
        bbox_ped_new = []
        image_path = None
        # image paths
        img_tensors = []
        hflip = True if float(torch.rand(1).item()) < self.hflip_p else False
        for i in range(len(frames)):
            anns = {'bbox': bbox[i]}
            vid = self.samples[index]['video_number']
            image_path = os.path.join(self.image_dir['JAAD'], vid, '{:05d}.png'.format(frames[i]))
            with open(image_path, 'rb') as f:
                img = PIL.Image.open(f).convert('RGB')
            if hflip:
                img = flip_image_and_bbox(img, anns)
            anns['bbox_ped'] =  copy.deepcopy(anns['bbox'])
            if self.preprocess is not None:
                img, anns = self.preprocess(img, anns)
            img_tensors.append(self._to_tensor(img))
            bbox_new.append(anns['bbox'])
            bbox_ped_new.append(anns['bbox_ped'])
    
        img_tensors = torch.stack(img_tensors)
        seq_len = img_tensors.size(0)
        # TODO: why not long?
        label = torch.tensor(label, dtype=torch.float32)

        sample = {'image': img_tensors, 'bbox': bbox_ped_new, 'bbox_ped': bbox_ped_new, 
                   'seq_length': seq_len, 'id':sample_id, 'label': label, 'attributes': attributes, 'action': action, 'behavior': behavior}

        return sample

    def __len__(self):
        return len(self.samples)