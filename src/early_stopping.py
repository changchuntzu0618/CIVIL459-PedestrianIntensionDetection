import torch
import os
import shutil

#based on https://github.com/Bjarten/early-stopping-pytorch/blob/master/pytorchtools.py
class EarlyStopping:
    """Early stops the training if validation loss doesn't improve after a given patience."""
    def __init__(self, checkpoint, patience=7, verbose=False, delta=0, min_loss=torch.inf):
        """
        :param
            patience (int): How long to wait after last time validation loss improved.
                            Default: 7
            verbose (bool): If True, prints a message for each validation loss improvement.
                            Default: False
            delta (float): Minimum change in the monitored quantity to qualify as an improvement.
                            Default: 0
        """
        self.patience = patience
        self.verbose = verbose
        self.counter = 0
        self.best_score = None if min_loss == torch.inf else  -min_loss
        self.early_stop = False
        self.delta = delta
        self.checkpoint = checkpoint

    def __call__(self, score, model, optimizer, epoch):

        if self.best_score is None:
            self.best_score = score
            self.save_checkpoint(score, model, optimizer, epoch)
        elif score <= self.best_score + self.delta:
            self.counter += 1
            print(f'EarlyStopping counter: {self.counter} out of {self.patience}')
            if self.counter >= self.patience:
                self.early_stop = True
        else:
            self.save_checkpoint(score, model, optimizer, epoch)
            self.best_score = score
            self.counter = 0

    def save_checkpoint(self, score, model, optimizer, epoch):
        """
        Saves model when validation loss decrease.
        """
        if self.verbose:
            print(f'Validation score changed  ({self.best_score:.6f} --> {score:.6f}).  Saving model ...')

        cp_dict = {
            'epoch': epoch,
            'optimizer_state_dict': optimizer.state_dict(),
            'score': score,
            'best_thr': model['best_thr'],
        }
        if 'encoder' in model:
            cp_dict['encoder_state_dict'] = model['encoder'].state_dict()
        if 'decoder' in model:
            cp_dict['decoder_state_dict'] = model['decoder'].state_dict()

        torch.save(cp_dict, self.checkpoint)
        

def load_from_checkpoint(model, save_path):
    device = torch.device('cpu') if not torch.cuda.is_available() else torch.device('cuda')
    checkpoint = torch.load(save_path, map_location=device)
    if 'encoder' in model:
        model['encoder'].load_state_dict(checkpoint['encoder_state_dict'])
    if 'decoder' in model:
        model['decoder'].load_state_dict(checkpoint['decoder_state_dict'])
    model['best_thr'] = checkpoint['best_thr']
