# mpes

Python-based data processing routines for static and time- and angle-resolved photoemission spectroscopy (ARPES &amp; trARPES)


In a photoemission process, an extreme UV or X-ray photon liberates an electron from the confines of the electronic potential within the material. [`ARPES`](https://en.wikipedia.org/wiki/Angle-resolved_photoemission_spectroscopy) directly measures the electronic energy and momentum parallel to the surface of the sample under study to infer the electronic states of the material. For a tutorial review on ARPES and its applications in physics and material science, see [`here`](http://www.phas.ubc.ca/~damascel/ARPES_Intro.pdf). The data structure of ARPES is a stack of 2D images measured at different sample geometries, which are used to reconstruct the full static 3D band structure of the material.


[`TrARPES`](http://ac.els-cdn.com/S036820481400108X/1-s2.0-S036820481400108X-main.pdf?_tid=00fe4a76-705f-11e7-aa2e-00000aacb35f&acdnat=1500894080_b61b6aadc82bb357e2797ddac6419991) is an emerging technique that combines state-of-the-art ultrafast laser systems (~ fs resolution) with an existing ARPES experimental setup. TrARPES studies light-induced electronic dynamics such as phase transition, exciton dynamics, reaction kinetics, etc. It adds a time dimension, usually on the order of femtoseconds to nanoseconds, to the scope of ARPES measurements. Due to complex electronic dynamics, various coupling effects between the energy and momentum dimensions come into play in time. A complete understanding of the multidimensional time series from trARPES measurements can reveal dynamic constants crucial to the understanding of material properties and aid in simulation, design and further device applications.

### Installation
```
pip install git+https://github.com/RealPolitiX/mpes.git
```
PyPI installation coming soon...

Documentation and examples will be posted [`here`](http://mpes.readthedocs.io/)

### Overview of submodules  
The mpes package contains the following submodules. They are listed here along with suggested import conventions
```
import mpes.fprocessing as fp  
import mpes.segmentation as seg
import mpes.visualization as vis
```
