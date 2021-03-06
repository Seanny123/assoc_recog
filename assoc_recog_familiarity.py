import nengo
import nengo.spa as spa
#import nengo_ocl
import numpy as np
import inspect, os, sys, time, csv, random
import matplotlib.pyplot as plt
from nengo_extras.vision import Gabor, Mask
import png
import itertools
import base64
import PIL.Image
import cStringIO


#### SETTINGS and VOCABS ######
nengo_gui_on = __name__ == '__builtin__'
ocl = False
extended_visual = True
 
if nengo_gui_on:
    cur_path = '/Users/Jelmer/Work/nengo/summerschool2016/jelmer'
else:
    cur_path = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe()))) # script path

if nengo_gui_on:
    fullexp = False #don't change this one, breaks the interface
else:
    fullexp = False



#display stimuli
def display_func(t, x):

    if np.size(x) > 14*90:
        input_shape = (1, 28, 90)
    else:
        input_shape = (1,14,90)

    values = x.reshape(input_shape)
    values = values.transpose((1, 2, 0))
    values = (values + 1) / 2 * 255.
    values = values.astype('uint8')

    if values.shape[-1] == 1:
        values = values[:, :, 0]

    png = PIL.Image.fromarray(values)
    buffer = cStringIO.StringIO()
    png.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue())

    display_func._nengo_html_ = '''
           <svg width="100%%" height="100%%" viewbox="0 0 %i %i">
           <image width="100%%" height="100%%"
                  xlink:href="data:image/png;base64,%s"
                  style="image-rendering: auto;">
           </svg>''' % (input_shape[2]*2, input_shape[1]*2, ''.join(img_str))




#load default stims (want to redo this for other subjs)
def load_stims(subj=0):

    #load file
    stims = np.genfromtxt(cur_path + '/stims/S' + str(subj) + 'Other.txt', skip_header=True,
                          dtype=[('probe', np.str_, 8), ('fan', 'int'), ('wordlen', np.str_, 8),
                                 ('item1', np.str_, 8), ('item2', np.str_, 8)], usecols=[1,2,3,4,5])
    stimsNFshort = np.genfromtxt(cur_path + '/stims/S' + str(subj) + 'NFShort.txt', skip_header=True,
                                 dtype=[('probe', np.str_, 8), ('fan', 'int'), ('wordlen', np.str_, 8),
                                        ('item1', np.str_, 8), ('item2', np.str_, 8)], usecols=[1,2,3,4,5])
    if fullexp:
        stimsNFlong = np.genfromtxt(cur_path + '/stims/S' + str(subj) + 'NFLong.txt', skip_header=True,
                                dtype=[('probe', np.str_, 8), ('fan', 'int'), ('wordlen', np.str_, 8),
                                       ('item1', np.str_, 8), ('item2', np.str_, 8)], usecols=[1,2,3,4,5])


    #combine
    if fullexp:
        stims = np.hstack((stims, stimsNFshort, stimsNFlong))
    else:
        stims = np.hstack((stims, stimsNFshort))

    stims = stims.tolist()
    #print stims
    #print stims2

    #get target pairs
    target_pairs = []
    for i in stims:
        if i[0] == 'Target':
            target_pairs.append((i[3],i[4]))

    return target_pairs, stims



#for real words, need at least 320
if fullexp:
    D = 256 #prob increase this later, increase n_neurons?
    Dmid = 128
    Dlow = 48
    [pairs, stims] = load_stims(1)
else:
    D = 96
    Dmid = 48
    Dlow = 32
    [pairs, stims] = load_stims(0)

target_rpfoils = []
new_foils = []
for i in stims:
    if i[0] != 'NewFoil':
        target_rpfoils.append(i)
    else:
        new_foils.append(i)


items = []
for i in stims:
    items.append(i[3])
    items.append(i[4])


# --- load the words
indir = cur_path + '/images/'
files = os.listdir(indir)
files2 = []
for fn in files:
    if fullexp:
        if fn[-4:] == '.png':
            files2.append(fn)
    else:
        if fn[-4:] == '.png' and (fn[:-4] in items):
            files2.append(fn)

y_train_words = []
X_train = np.empty(shape=(np.size(files2), 90*14),dtype='float32')
for i,fn in enumerate(files2):
        y_train_words.append(fn[:-4])
        r = png.Reader(indir + fn)
        r = r.asDirect()
        image_2d = np.vstack(itertools.imap(np.uint8, r[2]))
        image_2d /= 255
        image_1d = image_2d.reshape(1,90*14)
        X_train[i] = image_1d
        #plt.imshow(image_1d.reshape(14,90), vmin=0, vmax=1, cmap='gray')


y_train = np.asarray(range(0,len(np.unique(y_train_words))))
X_train = 2 * X_train - 1  # normalize to -1 to 1


# load vocabs
def initialize_vocabs():
    #global encoders
    global train_targets
    global vocab_concepts
    global vocab_goal
    global vocab_motor
    global vision_mapping
    global vocab_items
    global vocab_fingers
    global motor_mapping

    if extended_visual:
        #low level vision
        vocab_vision = nengo.spa.Vocabulary(Dmid,max_similarity=.5)
        for name in y_train_words:
            vocab_vision.parse(name)

        train_targets = vocab_vision.vectors


    #word concepts - should have all concepts, including new foils
    vocab_concepts = spa.Vocabulary(D, max_similarity=0.2)
    if extended_visual:
        for i in y_train_words:
            vocab_concepts.parse(i)
    else:
        for i in items:
            if i not in vocab_concepts.keys:
                vocab_concepts.parse(i)

    #vision-concept mapping
    if extended_visual:
        vision_mapping = np.zeros((D, Dmid))
        for word in y_train_words:
            vision_mapping += np.outer(vocab_vision.parse(word).v, vocab_concepts.parse(word).v).T

    #experimental items
    vocab_items = spa.Vocabulary(D, max_similarity = .2)
    for item1, item2 in pairs:
        vocab_items.parse(item1)
        vocab_items.parse(item2)

    print(vocab_concepts.keys )

    #experimental pairs
    vocab_pairs = spa.Vocabulary(D, max_similarity = .2)
    list_of_pairs = []
    for item1, item2 in pairs:
        vocab_pairs.parse('%s*ITEM1 + %s*ITEM2' % (item1, item2))
        vocab_pairs.add('%s_%s' % (item1,item2), vocab_pairs.parse('%s*ITEM1 + %s*ITEM2' % (item1, item2)))
        vocab_concepts.add('%s_%s' % (item1,item2), vocab_concepts.parse('%s*ITEM1 + %s*ITEM2' % (item1, item2)))
        list_of_pairs.append('%s_%s' % (item1,item2))

    #motor vocab, just for sim calcs
    vocab_motor = spa.Vocabulary(Dmid) #different dimension to be sure, upper motor hierarchy
    vocab_motor.parse('LEFT+RIGHT+INDEX+MIDDLE')

    vocab_fingers = spa.Vocabulary(Dlow) #direct finger activation
    vocab_fingers.parse('L1+L2+R1+R2')

    #map higher and lower motor
    motor_mapping = np.zeros((Dlow, Dmid))
    motor_mapping += np.outer(vocab_motor.parse('LEFT+INDEX').v, vocab_fingers.parse('L1').v).T
    motor_mapping += np.outer(vocab_motor.parse('LEFT+MIDDLE').v, vocab_fingers.parse('L2').v).T
    motor_mapping += np.outer(vocab_motor.parse('RIGHT+INDEX').v, vocab_fingers.parse('R1').v).T
    motor_mapping += np.outer(vocab_motor.parse('RIGHT+MIDDLE').v, vocab_fingers.parse('R2').v).T
    #mapping *= 0.5


    #goal vocab
    vocab_goal = spa.Vocabulary(Dlow)
    vocab_goal.parse('DO_TASK')
    vocab_goal.parse('RECOG')
    vocab_goal.parse('RESPOND')
    vocab_goal.parse('END')

    #attend vocab
    vocab_attend = spa.Vocabulary(D,max_similarity=.2)
    vocab_attend.parse('ITEM1')
    vocab_attend.parse('ITEM2')


    # --- set up network parameters
    if extended_visual:
        global n_vis
        global n_out
        global n_hid
        n_vis = X_train.shape[1] #nr of pixels, dimensions of network
        n_out = train_targets.shape[1] #nr of items
        n_hid = 1000  # nr of gabor encoders/neurons - recommendations?, one neuron per encoder

    if extended_visual:
        # random state to start
        rng = np.random.RandomState(9)
        global encoders
        encoders = Gabor().generate(n_hid, (11, 11), rng=rng)  # gabor encoders, work better, 11,11 apparently, why?
        encoders = Mask((14, 90)).populate(encoders, rng=rng,
                                           flatten=True)  # use them on part of the image (28x28 = input image)







#### MODEL ####
#model = spa.SPA()

global_item1 = 'GLOBAL1'
global_item2 = 'GLOBAL2'

def get_image(item):
    return X_train[y_train_words.index(item)]


def present_pair(t):
    im1 = get_image(global_item1)
    im2 = get_image(global_item2)
    return np.hstack((im1, im2))


def present_item(t):
    if t < .1:
        return get_image(global_item1)
    else:
        return get_image(global_item2)


def present_item_simple(t):
    if t < .1:
        return global_item1
    else:
        return global_item2


#def create_model(trial_info=('Target', 1, 'Short', 'METAL', 'SPARK'), hand='RIGHT',seedin=1):
def create_model(trial_info=('Target', 1, 'Short', 'CARGO', 'HOOD'), hand='LEFT', seedin=1):

    initialize_vocabs()
    print trial_info

    global global_item1
    global global_item2

    global_item1 = trial_info[3]
    global_item2 = trial_info[4]

    global model
    model = spa.SPA(seed=seedin)
    with model:

        #display current stimulus pair
        model.pair_input = nengo.Node(present_pair)
        model.pair_display = nengo.Node(display_func, size_in=model.pair_input.size_out)  # to show input
        nengo.Connection(model.pair_input, model.pair_display, synapse=None)


        #visual
        model.visual_net = nengo.Network()
        with model.visual_net:
            if not extended_visual:
                model.stimulus = spa.State(D, vocab=vocab_concepts,feedback=1)
                model.stim = spa.Input(stimulus=present_item_simple)
            else:

                #represent currently attended item
                model.attended_item = nengo.Node(present_item)
                model.vision_process = nengo.Ensemble(n_hid, n_vis, eval_points=X_train,
                                                        neuron_type=nengo.LIFRate(),
                                                        intercepts=nengo.dists.Choice([-0.5]), #can switch these off
                                                        max_rates=nengo.dists.Choice([100]),  # why?
                                                        encoders=encoders)
                                                                            #  1000 neurons, nrofpix = dimensions
                # visual_representation = nengo.Node(size_in=Dmid) #output, in this case 466 outputs
                model.visual_representation = nengo.Ensemble(n_hid, dimensions=Dmid)  # output, in this case 466 outputs

                model.visconn = nengo.Connection(model.vision_process, model.visual_representation, synapse=0.005,
                                                eval_points=X_train, function=train_targets,
                                                solver=nengo.solvers.LstsqL2(reg=0.01))
                nengo.Connection(model.attended_item, model.vision_process, synapse=None)


                # display attended item
                model.display_node = nengo.Node(display_func, size_in=model.attended_item.size_out)  # to show input
                nengo.Connection(model.attended_item, model.display_node, synapse=None)


        #control
        model.control_net = nengo.Network()
        with model.control_net:
            model.attend = spa.State(D, vocab=vocab_concepts, feedback=.5) #if attend item, goes to concepts
            model.goal = spa.State(D, vocab_goal, feedback=1) #current goal
            model.target_hand = spa.State(Dmid, vocab=vocab_motor, feedback=1)

        # concepts
        model.concepts = spa.AssociativeMemory(vocab_concepts,wta_output=True,wta_inhibit_scale=1)
        if not extended_visual:
            nengo.Connection(model.stimulus.output, model.concepts.input)
        else:
            nengo.Connection(model.visual_representation, model.concepts.input, transform=vision_mapping)

        # pair representation
        model.vis_pair = spa.State(D, vocab=vocab_concepts, feedback=1)

        model.dm_items = spa.AssociativeMemory(vocab_items) #familiarity should be continuous over all items, so no wta
        nengo.Connection(model.dm_items.output,model.dm_items.input,transform=.5,synapse=.01)

        model.familiarity = spa.State(1,feedback_synapse=.01) #no fb syn specified
        nengo.Connection(model.dm_items.am.elem_output,model.familiarity.input, #am.element_output == all outputs, we sum
                         transform=.8*np.ones((1,model.dm_items.am.elem_output.size_out)))

        #model.dm_pairs = spa.AssociativeMemory(vocab_concepts, input_keys=list_of_pairs,wta_output=True)
        #nengo.Connection(model.dm_items.output,model.dm_pairs.input)

        #motor
        model.motor_net = nengo.Network()
        with model.motor_net:

            #input multiplier
            model.motor_input = spa.State(Dmid,vocab=vocab_motor)

            #higher motor area (SMA?)
            model.motor = spa.State(Dmid, vocab=vocab_motor,feedback=1)

            #connect input multiplier with higher motor area
            nengo.Connection(model.motor_input.output,model.motor.input,synapse=.1,transform=10)

            #finger area
            model.fingers = spa.AssociativeMemory(vocab_fingers, input_keys=['L1', 'L2', 'R1', 'R2'], wta_output=True)

            #conncetion between higher order area (hand, finger), to lower area
            nengo.Connection(model.motor.output, model.fingers.input, transform=.4*motor_mapping)

            #finger position (spinal?)
            model.finger_pos = nengo.networks.EnsembleArray(n_neurons=50, n_ensembles=4)
            nengo.Connection(model.finger_pos.output, model.finger_pos.input, synapse=0.1, transform=0.3) #feedback

            #connection between finger area and finger position
            nengo.Connection(model.fingers.am.elem_output, model.finger_pos.input, transform=np.diag([0.55, .53, .57, .55])) #fix these



        model.bg = spa.BasalGanglia(
            spa.Actions(
                'dot(goal,DO_TASK)-.5 --> dm_items=vis_pair, goal=RECOG, attend=ITEM1',
                'dot(goal,RECOG)+dot(attend,ITEM1)+familiarity-2 --> goal=RECOG2, dm_items=vis_pair, attend=ITEM2',
                'dot(goal,RECOG)+dot(attend,ITEM1)+(1-familiarity)-2 --> goal=RECOG2, attend=ITEM2', #motor_input=1.5*target_hand+MIDDLE,
                'dot(goal,RECOG2)+dot(attend,ITEM2)+familiarity-1.3 --> goal=RESPOND, dm_items=vis_pair,motor_input=1.2*target_hand+INDEX, attend=ITEM2',
                'dot(goal,RECOG2)+dot(attend,ITEM2)+(1-familiarity)-1.3 --> goal=RESPOND, motor_input=1.5*target_hand+MIDDLE, attend=ITEM2',
                'dot(goal,RESPOND)+dot(motor,MIDDLE+INDEX)-1.4 --> goal=END',
                'dot(goal,END) --> goal=END',
                #'.6 -->',


            ))
        model.thalamus = spa.Thalamus(model.bg)

        model.cortical = spa.Cortical( # cortical connection: shorthand for doing everything with states and connections
            spa.Actions(
              #  'motor_input = .04*target_hand',
                #'dm_items = .8*concepts', #.5
                #'dm_pairs = 2*stimulus'
                'vis_pair = attend*concepts+concepts',
            ))


        #probes
        #model.pr_goal = nengo.Probe(model.goal.output,synapse=.01) #sample_every=.01 seconds, etc...
        model.pr_motor_pos = nengo.Probe(model.finger_pos.output,synapse=.01) #raw vector (dimensions x time)
        model.pr_motor = nengo.Probe(model.fingers.output,synapse=.01)
        model.pr_motor1 = nengo.Probe(model.motor.output, synapse=.01)
        #model.pr_target = nengo.Probe(model.target_hand.output, synapse=.01)

        #input
        model.input = spa.Input(goal=lambda t: 'DO_TASK' if t < 0.05 else '0',
                                target_hand=hand,
                                #attend=lambda t: 'ITEM1' if t < 0.1 else 'ITEM2',
                                )


        #return model
        ### END MODEL




##### EXPERIMENTAL CONTROL #####

results = []

def save_results(fname='output'):
    with open(cur_path + '/data/' + fname + '.txt', "w") as f:
        writer = csv.writer(f)
        writer.writerows(results)


def prepare_sim():

    print('\nModel preparation, ' + str(D) + ' dimensions and ' + str(len(vocab_concepts.keys)) + ' concepts...')
    #print(vocab_concepts.keys)

    start = time.clock()
    global sim


    if ocl:
        sim = nengo_ocl.Simulator(model)
    else:
        sim = nengo.Simulator(model)
    print('\t\t\t...finished in ' + str(round(time.clock() - start,2)) + ' seconds.\n')



#trial_info = target/foil, fan, word length, item 1, item 2
total_sim_time = 0

def do_trial(trial_info=('Target', 1, 'Short', 'METAL', 'SPARK'),hand='RIGHT'):

    global total_sim_time
    print('\nStart trial: ' + trial_info[0] + ', Fan ' + str(trial_info[1])
          + ', ' + trial_info[2] + ' - ' + ' '.join(trial_info[3:]) + ' - ' + hand + '\n')

    #run sim at least 100 ms
    sim.run(.1) #make this shorter than fastest RT

    print('Stepped sim started...\n')

    stepsize = 5 #ms
    resp = -1
    while sim.time < 1:

        # run stepsize ms, update time
        sim.run_steps(stepsize, progress_bar=False)

        #target_h = sim.data[model.pr_target][sim.n_steps-1]
        #print np.dot(target_h, vocab_motor['RIGHT'].v)

        #calc finger position
        last_motor_pos = sim.data[model.pr_motor_pos][sim.n_steps-1 ]
        position_finger = np.max(last_motor_pos)

        #print('\tFinger position (time = ' + str(sim.time) + '): ' + str(round(position_finger,3)))
        if position_finger >.68:
            break

    step = sim.n_steps

    '''
    sim_motor = [np.dot(sim.data[model.pr_motor1][step - 1], vocab_motor['RIGHT'].v),
                 np.dot(sim.data[model.pr_motor1][step - 1], vocab_motor['LEFT'].v),
                 np.dot(sim.data[model.pr_motor1][step - 1], vocab_motor['INDEX'].v),
                 np.dot(sim.data[model.pr_motor1][step - 1], vocab_motor['MIDDLE'].v)]

    if sim_motor[0] > sim_motor[1]:
        print '\nRight'
    else:
        print '\nLeft'
    if sim_motor[2] > sim_motor[3]:
        print 'Index'
    else:
        print 'Middle'
    '''

    # sims to L1, L2, R1, R2
    similarities = [np.dot(sim.data[model.pr_motor][step - 1], vocab_fingers['L1'].v),
                    np.dot(sim.data[model.pr_motor][step - 1], vocab_fingers['L2'].v),
                    np.dot(sim.data[model.pr_motor][step - 1], vocab_fingers['R1'].v),
                    np.dot(sim.data[model.pr_motor][step - 1], vocab_fingers['R2'].v)]
    # print similarities
    resp = np.argmax(similarities)
    if resp == 0:
        print '\nLeft Index'
    elif resp == 1:
        print '\nLeft Middle'
    elif resp == 2:
        print '\nRight Index'
    elif resp == 3:
        print '\nRight Middle'
    if resp == -1:
        print '\nNo response'
    print('\n... and done!')


    #resp 0 = left index, 1 = left middle, 2 = right index, 3 = right middle
    #change coding later
    if (trial_info[0] == 'Target' or trial_info[0] == 'RPFoil') and ((resp == 0 and hand == 'LEFT') or (resp == 2 and hand == 'RIGHT')):
        acc = 1
    elif (trial_info[0] == 'NewFoil') and ((resp == 1 and hand == 'LEFT') or (resp == 3 and hand == 'RIGHT')):
        acc = 1
    else:
        acc = 0

    print('\nRT = ' + str(sim.time) + ', acc = ' + str(acc))
    total_sim_time += sim.time
    results.append(trial_info + (hand, np.round(sim.time,3), acc, resp))



def do_1_trial(trial_info=('Target', 1, 'Short', 'METAL', 'SPARK'),hand='RIGHT'):

    global results
    total_sim_time = 0

    results = []

    start = time.clock()

    create_model(trial_info,hand)
    prepare_sim()
    do_trial(trial_info,hand)

    print('\nTotal time: ' + str(round(time.clock() - start,2)) + ' seconds for ' + str(total_sim_time) + ' seconds simulation.')
    sim.close()

    # save behavioral data
    print('\n')
    print(results)

    # data_motor_raw = sim.data[model.pr_motor]
    # data_motor = np.dot(data_motor_raw, model.get_output_vocab('motor'))





def do_4_trials():
    # type: () -> object
    global results
    global sim
    global model
    results = []

    start = time.clock()
    total_sim_time = 0

    stims_in = []
    for i in [0,33, 32,1]:
        stims_in.append(stims[i])

    hands_in = ['RIGHT','LEFT','RIGHT','LEFT']

    for i in range(4):
        cur_trial = stims_in[i]
        cur_hand = hands_in[i]
        create_model(cur_trial, cur_hand)
        prepare_sim()
        do_trial(cur_trial, cur_hand)
        sim.close()
        del(model)
        del(sim)

    print(
    '\nTotal time: ' + str(round(time.clock() - start, 2)) + ' seconds for ' + str(total_sim_time) + ' seconds simulation.')

    # data_motor_raw = sim.data[model.pr_motor]
    # data_motor = np.dot(data_motor_raw, model.get_output_vocab('motor'))

    # save behavioral data
    print('\n')
    save_results()



#target_rpfoils = []
#new_foils = []



def do_block(cur_hand='RIGHT'):
    global results
    results = []
    total_sim_time = 0
    start = time.clock()

    stims_in = target_rpfoils
    nr_trp = len(target_rpfoils)
    nr_nf = nr_trp / 4

    #add new foils
    stims_in = stims_in + random.sample(new_foils, nr_nf)

    #shuffle
    random.shuffle(stims_in)

    for i in stims_in:
        cur_trial = i
        create_model(cur_trial, cur_hand)
        prepare_sim()
        do_trial(cur_trial, cur_hand)
        sim.close()

    print(
    '\nTotal time: ' + str(round(time.clock() - start, 2)) + ' seconds for ' + str(total_sim_time) + ' seconds simulation.')

    # data_motor_raw = sim.data[model.pr_motor]
    # data_motor = np.dot(data_motor_raw, model.get_output_vocab('motor'))

    # save behavioral data
    print('\n')
    save_results('output' + '_' + cur_hand + '.txt')



#choice of trial, etc
if not nengo_gui_on:
    print 'nengo gui not on'
    #do_1_trial(trial_info=('NewFoil', 1, 'Short', 'CARGO', 'HOOD'),hand='LEFT')
    do_4_trials()

    #do_block('RIGHT')
    #do_block('LEFT')
else:
    print 'nengo gui on'
    initialize_vocabs()
    create_model()

