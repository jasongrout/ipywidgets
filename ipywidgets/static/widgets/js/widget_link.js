// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

define([
    "nbextensions/widgets/widgets/js/widget",
    "jquery",
], function(widget, $){

    var BaseLinkModel = widget.WidgetModel.extend({
        update_value: function(source, target) {
            if (this.updating) {
                return;
            }
            this.updating = true;
            try {
                if (target[0]) {
                    target[0].set(target[1], source[0].get(source[1]));
                    target[0].save_changes();
                }
            } finally {
                this.updating = false;
            }
        },

        cleanup: function() {
            // Unregister from change and destroy events of source and target.
            if (this.source) {
                this.source[0].off("change:" + this.source[1], null, this);
                this.source[0].off("destroy", null, this);
            }
            if (this.target) {
                this.target[0].off("change:" + this.target[1], null, this);
                this.target[0].off("destroy", null, this);
            }
        },

    }, {

        serializers: _.extend({
            target: {deserialize: widget.unpack_models},
            source: {deserialize: widget.unpack_models},
        }, widget.WidgetModel.serializers),

    });

    var LinkModel = BaseLinkModel.extend({

        initialize: function() {
            this.on("change", this.update_bindings, this);
            this.once("destroy", this.cleanup, this);
        },

        update_bindings: function() {
            this.cleanup();
            this.source = this.get("source");
            this.target = this.get("target");
            if (this.source) {
                this.source[0].on("change:" + this.source[1], function() {
                    this.update_value(this.source, this.target);
                }, this);
                this.update_value(this.source, this.target);
                this.source[0].once("destroy", this.cleanup, this);
            }
            if (this.target) {
                this.target[0].on("change:" + this.target[1], function() {
                    this.update_value(this.target, this.source);
                }, this);
                this.target[0].once("destroy", this.cleanup, this);
            }
        },

    });

    var DirectionalLinkModel = BaseLinkModel.extend({

        initialize: function() {
            this.on("change", this.update_bindings, this);
            this.once("destroy", this.cleanup, this);
        },

        update_bindings: function() {
            this.cleanup();
            this.source = this.get("source");
            this.target = this.get("target");
            if (this.source) {
                this.source[0].on("change:" + this.source[1], function() {
                    this.update_value(this.source, this.target);
                }, this);
                this.update_value(this.source, this.target);
                this.source[0].once("destroy", this.cleanup, this);
            }
            if (this.target) {
                this.target[0].once("destroy", this.cleanup, this);
            }
        },

    });

    return {
        "LinkModel": LinkModel,
        "DirectionalLinkModel": DirectionalLinkModel,
    }
});
