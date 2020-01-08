// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import {
    CoreDescriptionModel,
} from './widget_core';

import {
    DescriptionView, DescriptionStyleModel
} from './widget_description';

import {
    h, VirtualDOM
} from '@lumino/virtualdom';

import {
    uuid
} from './utils';

import * as _ from 'underscore';
import * as utils from './utils';
import $ from 'jquery';

export
class SelectionModel extends CoreDescriptionModel {
    defaults(): Backbone.ObjectHash {
        return {...super.defaults(),
            _model_name: 'SelectionModel',
            index: '',
            _options_labels: [],
            disabled: false,
        };
    }
}

export
class SelectionView extends DescriptionView {
    /**
     * Called when view is rendered.
     */
    render(): void {
        super.render(); // Incl. setting some defaults.
        this.el.classList.add('jupyter-widgets');
        this.el.classList.add('widget-inline-hbox');
    }

    /**
     * Update the contents of this view
     *
     * Called when the model is changed.  The model may have been
     * changed by another view or by a state update from the back-end.
     */
    update(): void {
        super.update();

        // Disable listbox if needed
        if (this.listbox) {
            this.listbox.disabled = this.model.get('disabled');
        }

        // Set tabindex
        this.updateTabindex();
    }

    updateTabindex(): void {
        if (!this.listbox) {
            return; // we might be constructing the parent
        }
        const tabbable = this.model.get('tabbable');
        if (tabbable === true) {
            this.listbox.setAttribute('tabIndex', '0');
        } else if (tabbable === false) {
            this.listbox.setAttribute('tabIndex', '-1');
        } else if (tabbable === null) {
            this.listbox.removeAttribute('tabIndex');
        }
    }

    listbox: HTMLSelectElement;
}

export
class DropdownModel extends SelectionModel {
    defaults(): Backbone.ObjectHash {
        return {...super.defaults(),
            _model_name: 'DropdownModel',
            _view_name: 'DropdownView',
            button_style: ''
        };
    }
}

// TODO: Make a Lumino dropdown control, wrapped in DropdownView. Also, fix
// bugs in keyboard handling. See
// https://github.com/jupyter-widgets/ipywidgets/issues/1055 and
// https://github.com/jupyter-widgets/ipywidgets/issues/1049
// For now, we subclass SelectView to provide DropdownView
// For the old code, see commit f68bfbc566f3a78a8f3350b438db8ed523ce3642

export
class DropdownView extends SelectionView {
    /**
     * Public constructor.
     */
    initialize(parameters: any): void {
        super.initialize(parameters);
        this.listenTo(this.model, 'change:_options_labels', () => this._updateOptions());
    }

    /**
     * Called when view is rendered.
     */
    render(): void {
        super.render();

        this.el.classList.add('widget-dropdown');

        this.listbox = document.createElement('select');
        this.listbox.id = this.label.htmlFor = uuid();
        this.el.appendChild(this.listbox);
        this._updateOptions();
        this.update();
    }

    /**
     * Update the contents of this view
     */
    update(): void {
        // Select the correct element
        const index = this.model.get('index');
        this.listbox.selectedIndex = index === null ? -1 : index;
        return super.update();
    }

    _updateOptions(): void {
        this.listbox.textContent = '';
        const items = this.model.get('_options_labels');
        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            const option = document.createElement('option');
            option.textContent = item.replace(/ /g, '\xa0'); // space -> &nbsp;
            option.setAttribute('data-value', encodeURIComponent(item));
            option.value = item;
            this.listbox.appendChild(option);
        }
    }

    events(): {[e: string]: string} {
        return {
            'change select': '_handle_change'
        };
    }

    /**
     * Handle when a new value is selected.
     */
    _handle_change(): void {
        this.model.set('index', this.listbox.selectedIndex === -1 ? null : this.listbox.selectedIndex);
        this.touch();
    }

    /**
     * Handle message sent to the front end.
     */
    handle_message(content: any): void {
        if (content.do == 'focus') {
            this.listbox.focus();
        } else if (content.do == 'blur') {
            this.listbox.blur();
        }
    }

    listbox: HTMLSelectElement;
}



export
class SelectModel extends SelectionModel {
    defaults(): Backbone.ObjectHash {
        return {...super.defaults(),
            _model_name: 'SelectModel',
            _view_name: 'SelectView',
            rows: 5
        };
    }
}

export
class SelectView extends SelectionView {
    /**
     * Public constructor.
     */
    initialize(parameters: any): void {
        super.initialize(parameters);
        this.listenTo(this.model, 'change:_options_labels', () => this._updateOptions());
        this.listenTo(this.model, 'change:index', (model, value, options) => this.updateSelection(options));
        // Create listbox here so that subclasses can modify it before it is populated in render()
        this.listbox = document.createElement('select');
    }

    /**
     * Called when view is rendered.
     */
    render(): void {
        super.render();
        this.el.classList.add('widget-select');

        this.listbox.id = this.label.htmlFor = uuid();
        this.el.appendChild(this.listbox);
        this._updateOptions();
        this.update();
        this.updateSelection();
    }

    /**
     * Update the contents of this view
     */
    update(): void {
        super.update();
        let rows = this.model.get('rows');
        if (rows === null) {
            rows = '';
        }
        this.listbox.setAttribute('size', rows);
    }

    updateSelection(options: any = {}): void {
        if (options.updated_view === this) {
            return;
        }
        const index = this.model.get('index');
        this.listbox.selectedIndex = index === null ? -1 : index;
    }

    _updateOptions(): void {
        this.listbox.textContent = '';
        const items = this.model.get('_options_labels');
        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            const option = document.createElement('option');
            option.textContent = item.replace(/ /g, '\xa0'); // space -> &nbsp;
            option.setAttribute('data-value', encodeURIComponent(item));
            option.value = item;
            this.listbox.appendChild(option);
        }
    }

    events(): {[e: string]: string} {
        return {
            'change select': '_handle_change'
        };
    }

    /**
     * Handle when a new value is selected.
     */
    _handle_change(): void {
        this.model.set('index', this.listbox.selectedIndex, {updated_view: this});
        this.touch();
    }
}

export
class RadioButtonsModel extends SelectionModel {
    defaults(): Backbone.ObjectHash {
        return {...super.defaults(),
            _model_name: 'RadioButtonsModel',
            _view_name: 'RadioButtonsView',
            tooltips: [],
            icons: [],
            button_style: ''
        };
    }
}


export
class RadioButtonsView extends DescriptionView {
    /**
     * Called when view is rendered.
     */
    render(): void {
        super.render();

        this.el.classList.add('widget-radio');

        this.container = document.createElement('div');
        this.el.appendChild(this.container);
        this.container.classList.add('widget-radio-box');

        this.update();
    }

    /**
     * Update the contents of this view
     *
     * Called when the model is changed.  The model may have been
     * changed by another view or by a state update from the back-end.
     */
    update(options?: any): void {

        const items: string[] = this.model.get('_options_labels');
        const checkedIndex = this.model.get('index');
        const disabled = this.model.get('disabled');
        const elements = items.map((item, index) => {
            const attr: any = {
                type: 'radio',
                value: index.toString(),
                dataset: {value: encodeURIComponent(item)},
                // checked: (checkedIndex === index) ? '' : null
            }
            if (checkedIndex === index) {
                attr['checked'] = '';
            }
            if (disabled) {
                attr['disabled'] = '';
            }
            console.log(attr);
            return h.label([item, h.input(attr)]);
        });
        console.log(elements);
        VirtualDOM.render(elements, this.container);


        // const radios = _.pluck(
        //     this.container.querySelectorAll('input[type="radio"]'),
        //     'value'
        // );
        // let stale = items.length != radios.length;

        // if (!stale) {
        //     for (let i = 0, len = items.length; i < len; ++i) {
        //         if (radios[i] !== items[i]) {
        //             stale = true;
        //             break;
        //         }
        //     }
        // }

        // if (stale && (options === undefined || options.updated_view !== this)) {
        //     // Add items to the DOM.
        //     this.container.textContent = '';
        //     items.forEach((item: any, index: number) => {
        //         const label = document.createElement('label');
        //         label.textContent = item;
        //         this.container.appendChild(label);

        //         const radio = document.createElement('input');
        //         radio.setAttribute('type', 'radio');
        //         radio.value = index.toString();
        //         radio.setAttribute('data-value', encodeURIComponent(item));
        //         label.appendChild(radio);
        //    });
        // }
        // items.forEach((item: any, index: number) => {
        //     const item_query = 'input[data-value="' +
        //         encodeURIComponent(item) + '"]';
        //         const radio = this.container.querySelectorAll(item_query);
        //     if (radio.length > 0) {
        //       const radio_el = radio[0] as HTMLInputElement;
        //       radio_el.checked = this.model.get('index') === index;
        //       radio_el.disabled = this.model.get('disabled');
        //     }
        // });

        // Schedule adjustPadding asynchronously to
        // allow dom elements to be created properly
        setTimeout(this.adjustPadding, 0, this);

        return super.update(options);
    }

    /**
     * Adjust Padding to Multiple of Line Height
     *
     * Adjust margins so that the overall height
     * is a multiple of a single line height.
     *
     * This widget needs it because radio options
     * are spaced tighter than individual widgets
     * yet we would like the full widget line up properly
     * when displayed side-by-side with other widgets.
     */
    adjustPadding(e: this): void {
        // Vertical margins on a widget
        const elStyles = window.getComputedStyle(e.el);
        const margins = parseInt(elStyles.marginTop, 10) + parseInt(elStyles.marginBottom, 10);

        // Total spaces taken by a single-line widget
        const lineHeight = e.label.offsetHeight + margins;

        // Current adjustment value on this widget
        const cStyles = window.getComputedStyle(e.container);
        const containerMargin = parseInt(cStyles.marginBottom);

        // How far we are off from a multiple of single windget lines
        const diff = (e.el.offsetHeight + margins - containerMargin) % lineHeight;

        // Apply the new adjustment
        const extraMargin = diff == 0 ? 0 : (lineHeight - diff);
        e.container.style.marginBottom = extraMargin + 'px';
    }

    events(): {[e: string]: string} {
        return {
            'click input[type="radio"]': '_handle_click'
        };
    }

    /**
     * Handle when a value is clicked.
     *
     * Calling model.set will trigger all of the other views of the
     * model to update.
     */
    _handle_click (event: Event): void {
        const target = event.target as HTMLInputElement;
        this.model.set('index', parseInt(target.value), {updated_view: this});
        this.touch();
        event.preventDefault();
    }

    container: HTMLDivElement;
}

export
class ToggleButtonsStyleModel extends DescriptionStyleModel {
    defaults(): Backbone.ObjectHash {
        return _.extend(super.defaults(), {
            _model_name: 'ToggleButtonsStyleModel',
        });
    }

    public static styleProperties = {
        ...DescriptionStyleModel.styleProperties,
        button_width: {
            selector: '.widget-toggle-button',
            attribute: 'width',
            default: null as any
        },
        font_weight: {
            selector: '.widget-toggle-button',
            attribute: 'font-weight',
            default: ''
        }
    };
}

export
 class ToggleButtonsModel extends SelectionModel {
    defaults(): Backbone.ObjectHash {
        return {...super.defaults(),
            _model_name: 'ToggleButtonsModel',
            _view_name: 'ToggleButtonsView'
        };
    }
}


export
class ToggleButtonsView extends DescriptionView {
    initialize(options: any): void {
        this._css_state = {};
        super.initialize(options);
        this.listenTo(this.model, 'change:button_style', this.update_button_style);
    }

    /**
     * Called when view is rendered.
     */
    render(): void {
        super.render();

        this.el.classList.add('widget-toggle-buttons');

        this.buttongroup = document.createElement('div');
        this.el.appendChild(this.buttongroup);

        this.update();
        this.set_button_style();
    }

    /**
     * Update the contents of this view
     *
     * Called when the model is changed.  The model may have been
     * changed by another view or by a state update from the back-end.
     */
    update(options?: any): void {
        const items: string[] = this.model.get('_options_labels');
        const icons = this.model.get('icons') || [];
        const previous_icons = this.model.previous('icons') || [];
        const previous_bstyle = (ToggleButtonsView.classMap as any)[this.model.previous('button_style')] || '';
        const tooltips = this.model.get('tooltips') || [];
        const disabled = this.model.get('disabled');
        const buttons = this.buttongroup.querySelectorAll('button');
        const values = _.pluck(buttons, 'value');
        let stale = false;

        for (let i = 0, len = items.length; i < len; ++i) {
            if (values[i] !== items[i] || icons[i] !== previous_icons[i]) {
                stale = true;
                break;
            }
        }

        if (stale && (options === undefined || options.updated_view !== this)) {
            // Add items to the DOM.
            this.buttongroup.textContent = '';
            items.forEach((item: any, index: number) => {
                let item_html;
                const empty = item.trim().length === 0 &&
                    (!icons[index] || icons[index].trim().length === 0);
                if (empty) {
                    item_html = '&nbsp;';
                } else {
                    item_html = utils.escape_html(item);
                }

                const icon = document.createElement('i');
                const button = document.createElement('button');
                if (icons[index]) {
                    icon.className = 'fa fa-' + icons[index];
                }
                button.setAttribute('type', 'button');
                button.className = 'widget-toggle-button jupyter-button';
                if (previous_bstyle) {
                    button.classList.add(previous_bstyle);
                }
                button.innerHTML = item_html;
                button.setAttribute('data-value', encodeURIComponent(item));
                button.setAttribute('value', index.toString());
                button.appendChild(icon);
                button.disabled = disabled;
                if (tooltips[index]) {
                    button.setAttribute('title', tooltips[index]);
                }
                this.update_style_traits(button);
                this.buttongroup.appendChild(button);
            });
        }

        // Select active button.
        items.forEach((item: any, index: number) => {
            const item_query = '[data-value="' + encodeURIComponent(item) + '"]';
            const button = this.buttongroup.querySelector(item_query);
            if (this.model.get('index') === index) {
                button.classList.add('mod-active');
            } else {
                button.classList.remove('mod-active');
            }
        });

        this.stylePromise.then(function(style) {
            if (style) {
                style.style();
            }
        });
        return super.update(options);
    }

    update_style_traits(button?: HTMLButtonElement): void {
        for (const name in this._css_state as string[]) {
            if (Object.prototype.hasOwnProperty.call(this._css_state, 'name')) {
                if (name === 'margin') {
                    this.buttongroup.style[name] = this._css_state[name];
                } else if (name !== 'width') {
                    if (button) {
                        button.style[name] = this._css_state[name];
                    } else {
                        const buttons = this.buttongroup
                            .querySelectorAll('button');
                        if (buttons.length) {
                            (buttons[0]).style[name] = this._css_state[name];
                        }
                    }
                }
            }
        }
    }

    update_button_style(): void {
        const buttons = this.buttongroup.querySelectorAll('button');
        for (let i = 0; i < buttons.length; i++) {
            this.update_mapped_classes(ToggleButtonsView.classMap, 'button_style', buttons[i]);
        }
    }

    set_button_style(): void {
        const buttons = this.buttongroup.querySelectorAll('button');
        for (let i = 0; i < buttons.length; i++) {
            this.set_mapped_classes(ToggleButtonsView.classMap, 'button_style', buttons[i]);
        }
    }

    events(): {[e: string]: string} {
        return {
            'click button': '_handle_click'
        };
    }

    /**
     * Handle when a value is clicked.
     *
     * Calling model.set will trigger all of the other views of the
     * model to update.
     */
    _handle_click(event: Event): void {
        const target = event.target as HTMLButtonElement;
        this.model.set('index', parseInt(target.value, 10), {updated_view: this});
        this.touch();
        // We also send a clicked event, since the value is only set if it changed.
        // See https://github.com/jupyter-widgets/ipywidgets/issues/763
        this.send({event: 'click'});
    }

    private _css_state: any;
    buttongroup: HTMLDivElement;
}

export
namespace ToggleButtonsView {
    export
    const classMap = {
        primary: ['mod-primary'],
        success: ['mod-success'],
        info: ['mod-info'],
        warning: ['mod-warning'],
        danger: ['mod-danger']
    };
}


export
class SelectionSliderModel extends SelectionModel {
    defaults(): Backbone.ObjectHash {
        return {...super.defaults(),
            _model_name: 'SelectionSliderModel',
            _view_name: 'SelectionSliderView',
            orientation: 'horizontal',
            readout: true,
            continuous_update: true
        };
    }
}


export
class SelectionSliderView extends DescriptionView {
    /**
     * Called when view is rendered.
     */
    render(): void {
        super.render();

        this.el.classList.add('widget-hslider');
        this.el.classList.add('widget-slider');

        (this.$slider = $('<div />') as any)
            .slider({
                slide: this.handleSliderChange.bind(this),
                stop: this.handleSliderChanged.bind(this)
            })
            .addClass('slider');

        // Put the slider in a container
        this.slider_container = document.createElement('div');
        this.slider_container.classList.add('slider-container');
        this.slider_container.appendChild(this.$slider[0]);
        this.el.appendChild(this.slider_container);

        this.readout = document.createElement('div');
        this.el.appendChild(this.readout);
        this.readout.classList.add('widget-readout');
        this.readout.style.display = 'none';

        this.listenTo(this.model, 'change:slider_color', (sender, value) => {
            this.$slider.find('a').css('background', value);
        });

        this.$slider.find('a').css('background', this.model.get('slider_color'));

        // Set defaults.
        this.update();
    }

    /**
     * Update the contents of this view
     *
     * Called when the model is changed.  The model may have been
     * changed by another view or by a state update from the back-end.
     */
    update(options?: any): void {
        if (options === undefined || options.updated_view !== this) {
            const labels = this.model.get('_options_labels');
            const max = labels.length - 1;
            const min = 0;
            this.$slider.slider('option', 'step', 1);
            this.$slider.slider('option', 'max', max);
            this.$slider.slider('option', 'min', min);

            // WORKAROUND FOR JQUERY SLIDER BUG.
            // The horizontal position of the slider handle
            // depends on the value of the slider at the time
            // of orientation change.  Before applying the new
            // workaround, we set the value to the minimum to
            // make sure that the horizontal placement of the
            // handle in the vertical slider is always
            // consistent.
            const orientation = this.model.get('orientation');
            this.$slider.slider('option', 'value', min);
            this.$slider.slider('option', 'orientation', orientation);

            const disabled = this.model.get('disabled');
            this.$slider.slider('option', 'disabled', disabled);
            if (disabled) {
                this.readout.contentEditable = 'false';
            } else {
                this.readout.contentEditable = 'true';
            }

            // Use the right CSS classes for vertical & horizontal sliders
            if (orientation === 'vertical') {
                this.el.classList.remove('widget-hslider');
                this.el.classList.remove('widget-inline-hbox');
                this.el.classList.add('widget-vslider');
                this.el.classList.add('widget-inline-vbox');
            } else {
                this.el.classList.remove('widget-vslider');
                this.el.classList.remove('widget-inline-vbox');
                this.el.classList.add('widget-hslider');
                this.el.classList.add('widget-inline-hbox');
            }

            const readout = this.model.get('readout');
            if (readout) {
                // this.$readout.show();
                this.readout.style.display = '';
            } else {
                // this.$readout.hide();
                this.readout.style.display = 'none';
            }
            this.updateSelection();

        }
        return super.update(options);
    }

    events(): {[e: string]: string} {
        return {
            'slide': 'handleSliderChange',
            'slidestop': 'handleSliderChanged'
        };
    }

    updateSelection(): void {
        const index = this.model.get('index');
        this.$slider.slider('option', 'value', index);
        this.updateReadout(index);
    }

    updateReadout(index: any): void {
        const value = this.model.get('_options_labels')[index];
        this.readout.textContent = value;
    }

    /**
     * Called when the slider value is changing.
     */
    handleSliderChange(e: Event, ui: { value?: number; values?: number[] }): void {
        this.updateReadout(ui.value);

        // Only persist the value while sliding if the continuous_update
        // trait is set to true.
        if (this.model.get('continuous_update')) {
            this.handleSliderChanged(e, ui);
        }
    }

    /**
     * Called when the slider value has changed.
     *
     * Calling model.set will trigger all of the other views of the
     * model to update.
     */
    handleSliderChanged(e: Event, ui: { value?: number; values?: number[] }): void {
        this.updateReadout(ui.value);
        this.model.set('index', ui.value, {updated_view: this});
        this.touch();
    }

    $slider: any;
    slider_container: HTMLDivElement;
    readout: HTMLDivElement;
}

export
class MultipleSelectionModel extends SelectionModel {
    defaults(): Backbone.ObjectHash {
        return { ...super.defaults(),
            _model_name: 'MultipleSelectionModel',
        };
    }
}


export
class SelectMultipleModel extends MultipleSelectionModel {
    defaults(): Backbone.ObjectHash {
        return {...super.defaults(),
            _model_name: 'SelectMultipleModel',
            _view_name: 'SelectMultipleView',
            rows: null
        };
    }
}

export
class SelectMultipleView extends SelectView {
    /**
     * Public constructor.
     */
    initialize(parameters: any): void {
        super.initialize(parameters);
        this.listbox.multiple = true;
    }

    /**
     * Called when view is rendered.
     */
    render(): void {
        super.render();
        this.el.classList.add('widget-select-multiple');
    }

    updateSelection(options: any = {}): void {
        if (options.updated_view === this) {
            return;
        }
        const selected = this.model.get('index') || [];
        const listboxOptions = this.listbox.options;
        // Clear the selection
        this.listbox.selectedIndex = -1;
        // Select the appropriate options
        selected.forEach((i: number) => {
            listboxOptions[i].selected = true;
        });
    }

    /**
     * Handle when a new value is selected.
     */
    _handle_change(): void {
        const index = Array.prototype.map
            .call(this.listbox.selectedOptions || [], function(option: HTMLOptionElement) {
                return option.index;
            });
        this.model.set('index', index, {updated_view: this});
        this.touch();
    }
}

export
class SelectionRangeSliderModel extends MultipleSelectionModel {
    defaults(): Backbone.ObjectHash {
        return {...super.defaults(),
            _model_name: 'SelectionSliderModel',
            _view_name: 'SelectionSliderView',
            orientation: 'horizontal',
            readout: true,
            continuous_update: true
        };
    }
}


export
class SelectionRangeSliderView extends SelectionSliderView {
    /**
     * Called when view is rendered.
     */
    render(): void {
        super.render();
        this.$slider.slider('option', 'range', true);
    }

    updateSelection(): void {
        const index = this.model.get('index');
        this.$slider.slider('option', 'values', index.slice());
        this.updateReadout(index);
    }

    updateReadout(index: number[]): void {
        const labels = this.model.get('_options_labels');
        const minValue = labels[index[0]];
        const maxValue = labels[index[1]];
        this.readout.textContent = `${minValue}-${maxValue}`;
    }

    /**
     * Called when the slider value is changing.
     */
    handleSliderChange(e: Event, ui: { values: number[] }): void {
        this.updateReadout(ui.values);

        // Only persist the value while sliding if the continuous_update
        // trait is set to true.
        if (this.model.get('continuous_update')) {
            this.handleSliderChanged(e, ui);
        }
    }

    /**
     * Called when the slider value has changed.
     *
     * Calling model.set will trigger all of the other views of the
     * model to update.
     */
    handleSliderChanged(e: Event, ui: { values: number[] }): void {
        // The jqueryui documentation indicates ui.values doesn't exist on the slidestop event,
        // but it appears that it actually does: https://github.com/jquery/jquery-ui/blob/ae31f2b3b478975f70526bdf3299464b9afa8bb1/ui/widgets/slider.js#L313
        this.updateReadout(ui.values);
        this.model.set('index', ui.values.slice(), {updated_view: this});
        this.touch();
    }

    $slider: any;
    slider_container: HTMLDivElement;
    readout: HTMLDivElement;
}
